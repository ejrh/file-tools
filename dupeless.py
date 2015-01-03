import sys
import os
import time
import wx
import hashlib
import threading
import ObjectListView as olv


class Options(object):
    def __init__(self, use_md5, use_header_md5):
        self.use_md5 = use_md5
        self.use_header_md5 = use_header_md5


class Item(object):
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.md5 = None
        self.embellished = False
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return self.name == other.name and self.size == other.size and self.md5 == other.md5


class Duplicates(object):
    def __init__(self, options):
        self.options = options
        self.results = {}
        self.num_items = 0
    
    def search(self, path, update_callback=None):
        num_items = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                full_name = os.path.join(dirpath, filename)
                item = self.create_item(full_name)
                self.add_item(item)
                if update_callback is not None and not update_callback(self.num_items):
                    return
    
    def add_item(self, item):
        key = self.make_key(item)
        if key not in self.results:
            items = set()
            self.results[key] = items
        else:
            items = self.results[key]
        
        if item in items:
            return
        
        if self.options.use_md5 and len(items) == 1 and not item.embellished:
            del self.results[key]
            self.num_items -= 1
            old_item = items.pop()
            if self.embellish_item(old_item):
                self.add_item(old_item)
            if self.embellish_item(item):
                self.add_item(item)
        else:
            items.add(item)
            self.num_items += 1

    def create_item(self, name):
        size = os.path.getsize(name)
        return Item(name, size)
    
    def embellish_item(self, item):
        item.embellished = True
        try:
            fd = open(item.name, 'rb')
            m = hashlib.md5()
            BUFSIZE = 1048576
            while True:
                buf = fd.read(BUFSIZE)
                m.update(buf)
                if len(buf) == 0 or self.options.use_header_md5:
                    break
            fd.close()
            item.md5 = m.hexdigest()
        except IOError:
            return False
        return True
    
    def make_key(self, item):
        if self.options.use_md5:
            return (item.size, item.md5)
        return (item.size,)
    
    def remove(self, item):
        key = self.make_key(item)
        self.results[key].remove(item)
        self.num_items -= 1


class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super(MainFrame, self).__init__(parent, -1, title, size=wx.Size(800,600),
                          style=wx.DEFAULT_FRAME_STYLE | wx.NO_FULL_REPAINT_ON_RESIZE)
    
        menu_bar = wx.MenuBar()

        clear_id = wx.NewId()
        choose_dir_id = wx.NewId()
        search_id = wx.NewId()
        delete_id = wx.NewId()
        file_menu = wx.Menu()
        file_menu.Append(clear_id, "&Clear results\tCtrl-N", "Clear results and start a new search")
        file_menu.Append(choose_dir_id, "&Choose directory...\tCtrl-D", "Choose directory to search in")
        file_menu.Append(search_id, "&Search\tCtrl-S", "Search for duplicates")
        file_menu.Append(delete_id, "&Delete\tCtrl-X", "Delete marked files")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt-F4", "Exit this program")
        menu_bar.Append(file_menu, "&File")
        self.Bind(wx.EVT_MENU, self.OnClear, id=clear_id)
        self.Bind(wx.EVT_MENU, self.OnChooseDir, id=choose_dir_id)
        self.Bind(wx.EVT_MENU, self.OnSearch, id=search_id)
        self.Bind(wx.EVT_MENU, self.OnDelete, id=delete_id)
        self.Bind(wx.EVT_MENU, self.OnFileExit, id=wx.ID_EXIT)
        
        use_md5_id = wx.NewId()
        use_header_md5_id = wx.NewId()
        options_menu = wx.Menu()
        options_menu.Append(use_md5_id, "Use &MD5", "Compare files using their MD5 digests", wx.ITEM_CHECK)
        options_menu.Append(use_header_md5_id, "Use &header MD5", "Compare files using the MD5 digest of their headers", wx.ITEM_CHECK)
        menu_bar.Append(options_menu, "&Options")
        self.Bind(wx.EVT_MENU, self.OnUseMD5, id=use_md5_id)
        self.Bind(wx.EVT_MENU, self.OnUseHeaderMD5, id=use_header_md5_id)
        
        self.SetMenuBar(menu_bar)
    
        self.CreateStatusBar()
        
        panel = wx.Panel(self)
        
        self.list = olv.ObjectListView(panel, wx.ID_ANY, style=wx.LC_REPORT)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list, 1, wx.ALL | wx.EXPAND)
        panel.SetSizer(sizer)
        
        self.use_md5 = False
        self.use_header_md5 = False
        self.dir = None
        self.OnClear(None)
    
    def OnClear(self, event):
        self.dupes = Duplicates(None)
        self.update_options()
        self.update_results()
    
    def OnChooseDir(self, event):
        dlg = wx.DirDialog(self, "Choose a directory:",
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.dir = dlg.GetPath()

        dlg.Destroy()
    
    def OnSearch(self, event):
        if not self.dir:
            return
        
        dlg = wx.ProgressDialog("Searching for duplicates...",
                               "",
                               parent=self,
                               style = wx.PD_CAN_ABORT
                                | wx.PD_APP_MODAL
                                | wx.PD_ELAPSED_TIME
                                )

        def do_update(num_items):
            return not self.search_cancelled
        
        def do_search():
            self.dupes.search(self.dir, do_update)
            self.search_cancelled = True
        
        self.search_cancelled = False
        thread = threading.Thread(target=do_search)
        thread.start()
        while not self.search_cancelled:
            wx.MilliSleep(100)
            cont, skip = dlg.Pulse("Found %d items, %d dupes" % (self.dupes.num_items, self.dupes.num_items - len(self.dupes.results)))
            if not cont:
                self.search_cancelled = True
        thread.join()
        
        dlg.Destroy()
        
        self.update_results()
    
    def OnDelete(self, event):
        for item in self.list.GetObjects():
            if self.list.GetCheckState(item):
                try:
                    os.unlink(item.name)
                except WindowsError, ex:
                    print >>sys.stderr, ex
                    pass
                self.dupes.remove(item)
        self.update_results()
    
    def OnUseMD5(self, event):
        self.use_md5 = event.IsChecked()
        self.update_options()
    
    def OnUseHeaderMD5(self, event):
        self.use_header_md5 = event.IsChecked()
        self.update_options()
    
    def update_options(self):
        self.dupes.options = Options(self.use_md5, self.use_header_md5)

    def update_results(self):
        self.list.SetColumns([
            olv.ColumnDefn("Name", "left", 200, "name", isSpaceFilling=True),
            olv.ColumnDefn("Size", "right", -1, "size"),
            olv.ColumnDefn("MD5", "left", -1, "md5"),
            olv.ColumnDefn("Group", "right", -1, "group_id"),
        ])
        
        self.list.CreateCheckStateColumn()
 
        objs = []
        next_group_id = 1
        for key in reversed(sorted(self.dupes.results.keys())):
            if len(self.dupes.results[key]) <= 1:
                continue
            
            for item in self.dupes.results[key]:
                item.group_id = next_group_id
                objs.append(item)
            next_group_id += 1
                
        self.list.SetObjects(objs)
        
        silver = wx.Colour(240, 240, 240)
        def row_formatter(list_item, obj):
            if obj.group_id % 2 == 0:
                list_item.SetBackgroundColour(silver)
            else:
                list_item.SetBackgroundColour(wx.WHITE)

        self.list.rowFormatter = row_formatter
        
        self.list.AutoSizeColumns()
        self.Layout()
        
    
    def OnFileExit(self, event):
        self.Close()


class Application(wx.App):
    def __init__(self):
        super(Application, self).__init__(redirect=False)
    
    def OnInit(self):
        frame = MainFrame(None, "Duplicate File Finder")
        frame.Show()
        
        return True


def main(args):
    app = Application()
    app.MainLoop()


if __name__ == '__main__':
    main(sys.argv)
