import os
import hashlib
from optparse import OptionParser


class File(object):
    def __init__(self, filename):
        self.filename = filename
        stats = os.stat(filename)
        self.size = stats.st_size
        self.inode = (stats.st_dev, stats.st_ino)
        self.num_links = stats.st_nlink
        self.hash = None
    
    def calc_hash(self):
        hashing = hashlib.sha1()
        with open(self.filename, 'rb') as f:
            while True:
                data = f.read(1024*1024)
                if len(data) == 0:
                    break
                hashing.update(data)
        self.hash = hashing.hexdigest()
        return self.hash
    
    def __str__(self):
        return self.filename


class Deduper(object):
    def __init__(self, options):
        self.options = options
        # Files is a three-level dictionary on file size, hash, inode, to a list of File items.
        # (Inode is also used as a key at second level.)
        self.files = {}
        self.duplicates = {}

    def collect_files(self, dir):
        for dirpath, dirnames, filenames in os.walk(dir):
            for fn in filenames:
                file_path = os.path.join(dirpath, fn)
                if not self.options.all and fn.startswith('.'):
                    if self.options.verbose:
                        print 'Skipping %s' % file_path
                    continue
                self.add_file(file_path)
    
    def add_file(self, filename):
        item = File(filename)
        
        # Easy case: file is first of its size
        if item.size not in self.files:
            item_list = [item]
            self.files[item.size] = {
                item.hash: { item.inode: item_list },
                item.inode: item_list
            }
            if self.options.verbose:
                print 'Added %s' % filename
            return

        entry = self.files[item.size]
        
        # Easy-ish case: file's inode is already present
        if item.inode in entry:
            item.hash = entry[item.inode][0].hash
            entry[item.inode].append(item)
            if self.options.verbose:
                print 'Added %s (already linked)' % filename
            return
        
        # Entry has some unhashed items; hash them now
        if None in entry:
            if self.options.verbose:
                print 'Hashing files of size %d' % item.size
            
            inode_map = entry[None]
            del entry[None]
            for inode,item_list in inode_map.items():
                # Calculate hash for this inode's list
                list_hash = item_list[0].calc_hash()
                for item in item_list[1:]:
                    item.hash = list_hash
                
                if list_hash in entry:
                    entry[list_hash][inode] = item_list
                else:
                    entry[list_hash] = { inode: item_list }
        
        item_hash = item.calc_hash()
        item_list = [item]
        if item_hash in entry:
            entry[item_hash][item.inode] = item_list
            entry[item.inode] = item_list
        else:
            entry[item_hash] = { item.inode: item_list }
            entry[item.inode] = item_list

        if self.options.verbose:
            print 'Added %s (hash %s)' % (filename, item.hash)

    def print_files(self):
        for size,hash_map in sorted(self.files.items()):
            print '%d:' % size
            for hash,entry in sorted(hash_map.items()):
                print '    %s:' % str(hash)
                if isinstance(entry, dict):
                    for inode,item_list in sorted(entry.items()):
                        print '        %s:' % str(inode)
                        print '        %s' % ','.join(str(x) for x in item_list)
                else:
                    print '    %s' % ','.join(str(x) for x in entry)

    def calc_duplicates(self):
        for size,hash_map in sorted(self.files.items()):
            # Unhashed items mean there is nothing to dedupe for this size
            if None in hash_map:
                continue
            
            for hash,inode_map in sorted(hash_map.items()):
                if not isinstance(inode_map, dict):
                    continue
                
                if len(inode_map) < 2:
                    continue
                
                self.duplicates[hash] = inode_map.items()
                for inode,item_list in sorted(inode_map.items()):
                    if self.options.verbose:
                        print hash, inode, ','.join(str(x) for x in item_list)
    
    def create_links(self):
        for hash,dupes in self.duplicates.items():
            first_inode,first_item_list = dupes[0]
            first_item = first_item_list[0]
            for inode,item_list in dupes[1:]:
                source = first_item.filename
                for item in item_list:
                    target = item.filename
                    temp = target + '.tmp'
                    if self.options.verbose:
                        print 'Link to %s from %s' % (source, target)
                    if self.options.execute:
                        os.link(source, temp)
                        os.rename(temp, target)

def main():
    usage = """usage: %prog PATHS..."""
    desc = """Find duplicate files and turn them into hardlinks"""
    parser = OptionParser(usage=usage, description=desc)
    parser.add_option("-a", "--all",
                      action="store_true", dest="all", default=False,
                      help="process all files (including .hidden)")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="enable verbose output")
    parser.add_option("-x", "--execute",
                      action="store_true", dest="execute", default=False,
                      help="execute creation of links")
    
    options, args = parser.parse_args()
    if len(args) == 0:
        parser.error("No paths specified")
    
    deduper = Deduper(options)
    for dir in args:
        deduper.collect_files(dir)

    deduper.calc_duplicates()
    
    deduper.create_links()


if __name__ == '__main__':
    main()
