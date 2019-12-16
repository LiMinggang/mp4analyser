"""
mp4analyser.py

A tkinter application that allows inspection of MP4 files that conform to ISO/IEC 14496-12

This file generates the user interface, and contains the callback functions that respond to user events.


"""

import os
import logging
import json
import binascii
import traceback
from tkinter import *
from tkinter import filedialog
from tkinter import simpledialog
from tkinter import messagebox
from tkinter import ttk
# mp4 is the package that actually parses the mp4 file
import mp4.iso

try:
    from idlelib.redirector import WidgetRedirector
except ImportError:
    raise Exception("Python > 3.6 needed. Also idle3 needs to be installed on your system")


# From http://effbot.org/zone/tkinter-autoscrollbar.htm
# a scrollbar that hides itself if it's not needed.  only
# works if you use the grid geometry manager.
class AutoScrollbar(ttk.Scrollbar):

    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            # grid_remove is currently missing from Tkinter!
            self.tk.call("grid", "remove", self)
        else:
            self.grid()
        Scrollbar.set(self, lo, hi)


# See https://stackoverflow.com/questions/3842155/is-there-a-way-to-make-the-tkinter-text-widget-read-only
# note idle3 dependency
class ReadOnlyText(Text):

    def __init__(self, *args, **kwargs):
        Text.__init__(self, *args, **kwargs)
        self.redirector = WidgetRedirector(self)
        self.insert = self.redirector.register("insert", lambda *args, **kw: "break")
        self.delete = self.redirector.register("delete", lambda *args, **kw: "break")


class MyApp(Tk):

    def __init__(self):
        super().__init__()
        # uncomment desired logging level
        # logging.basicConfig(format = "%(asctime)s %(message)s", level=logging.DEBUG)
        logging.basicConfig(format = "%(asctime)s %(message)s", level=logging.WARNING)

        self.mp4file = None
        self.dialog_dir = os.getcwd()#os.path.expanduser("~")
        self.search_menu = "Search"
        self.find_menu = "Find Box..."
        self.find_next_menu = "Find Next Box"
        self.find_prev_menu = "Finx Prev Box"

        # build ui
        self.title("MP4 Analyser")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.geometry('1300x700')

        # build a menu bar
        self.option_add('*tearOff', FALSE)
        self.menubar = Menu(self)

        self.filemenu = Menu(self.menubar)
        self.filemenu.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_file)
        self.bind_all("<Control-o>", self.open_file)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", accelerator="Alt+X", command=self.quit)
        self.bind_all("<Alt-x>", self.find_box)
        self.menubar.add_cascade(label="File", menu=self.filemenu)
        self.findmenu = Menu(self.menubar)
        self.findmenu.add_command(label="Find Box...", accelerator="Ctrl+F", command=self.find_box, state=DISABLED)
        self.bind_all("<Control-f>", self.find_box)
        self.findmenu.add_command(label=self.find_next_menu, accelerator="F3", command=self.find_next_box, state=DISABLED)
        self.bind_all("<F3>", self.find_next_box)
        self.findmenu.add_command(label=self.find_prev_menu, accelerator="F4", command=self.find_prev_box, state=DISABLED)
        self.bind_all("<F4>", self.find_prev_box)
        self.menubar.add_cascade(label="Search", menu=self.findmenu)
        self.config(menu=self.menubar)

        # status bar
        self.statustext = StringVar()
        self.statustext.set("")
        self.status = Label(self, textvariable=self.statustext, bd=1, anchor=W)
        self.status.grid(column=0, row=1, columnspan=2, sticky=(W, E, S))

        # create left-right paned window
        self.p = ttk.Panedwindow(self, orient=HORIZONTAL)
        self.p.grid(column=0, row=0, sticky=(N, W, E, S))

        # create left-right paned window
        self.p1 = ttk.Panedwindow(self.p, orient=VERTICAL)
        self.p1.grid(column=0, row=0, sticky=(N, W, E, S))

        # first pane shown on left:
        self.f1 = ttk.Labelframe(self.p, text='Box Hierarchy')
        self.f1.grid(column=0, row=0, sticky=(N, W, E, S))
        self.f1.columnconfigure(0, weight=1)
        self.f1.rowconfigure(0, weight=1)

        # box details shown top right
        self.f2 = ttk.Labelframe(self.p1, text='Box Details', width=750, )  # second pane
        self.f2.grid(column=0, row=0, sticky=(N, W, E, S))
        self.f2.columnconfigure(0, weight=1)
        self.f2.rowconfigure(0, weight=1)

        # hex view shown bottom right
        self.f3 = ttk.Labelframe(self.p1, text='Hex View', width=750, )  # second pane
        self.f3.grid(column=0, row=0, sticky=(N, W, E, S))
        self.f3.columnconfigure(0, weight=1)
        self.f3.rowconfigure(0, weight=1)

        # add seems to work left to right, top to bottom
        self.p.add(self.f1)
        self.p.add(self.p1)
        self.p1.add(self.f2)
        self.p1.add(self.f3)

        # tree view showing box hierarchy
        self.tree = ttk.Treeview(self.f1, show="tree")
        self.tree.grid(column=0, row=0, sticky=(N, W, E, S))
        self.tree.column("#0", width=300)
        self.treenodes = []

        # Sub-classed auto hiding scroll bar
        self.scroll1 = AutoScrollbar(self.f1, orient=VERTICAL, command=self.tree.yview)
        self.scroll1.grid(column=1, row=0, sticky=(N, S))
        self.tree['yscrollcommand'] = self.scroll1.set
        self.tree.bind('<ButtonRelease-1>', self.select_box)

        # text widget display details of selected box
        self.t = ReadOnlyText(self.f2, state='normal', width=120, height=24, wrap='none')
        self.t.grid(column=0, row=0, sticky=(N, W, E, S))
        self.t.tag_configure('error', font=('Arial', 12, 'bold', 'italic'), foreground='red')

        # Sub-classed auto hiding scroll bar
        self.scroll2 = AutoScrollbar(self.f2, orient=VERTICAL, command=self.t.yview)
        self.scroll2.grid(column=1, row=0, sticky=(N, S))
        self.t['yscrollcommand'] = self.scroll2.set

        # text widget displaying hex
        self.thex = ReadOnlyText(self.f3, state='normal', width=120, height=15, wrap='none')
        self.thex.grid(column=0, row=0, sticky=(N, W, E, S))

        # Sub-classed auto hiding scroll bar
        self.scroll3 = AutoScrollbar(self.f3, orient=VERTICAL, command=self.thex.yview)
        self.scroll3.grid(column=1, row=0, sticky=(N, S))
        self.thex['yscrollcommand'] = self.scroll3.set

        # Sub-classed auto hiding scroll bar
        self.scroll4 = AutoScrollbar(self.f3, orient=HORIZONTAL, command=self.thex.xview)
        self.scroll4.grid(column=0, row=1, sticky=(W, E))
        self.thex['xscrollcommand'] = self.scroll4.set

    def open_file(self, event=None):
        """ Callback on selecting 'Open' from menu """
        filename = filedialog.askopenfilename(filetypes=(("MP4 Files", ".mp4 .m4a .m4p .m4b .m4r .m4v"),
                                                         ("All Files", "*.*")), initialdir=self.dialog_dir)
        if not filename:
            return
        logging.debug("Loading file " + filename)
        self.statustext.set("Loading...")
        self.update_idletasks()
        self.mp4file = mp4.iso.Mp4File(filename)
        logging.debug("Finished loading file " + filename)
        self.dialog_dir, filename_base = os.path.split(filename)
        self.title("MP4 Analyser" + " - " + filename_base)
        # Clear tree and text widgets if not empty
        self.tree.delete(*self.tree.get_children())
        self.treenodes.clear()
        self.t.delete(1.0, END)
        self.thex.delete(1.0, END)

        self.findmenu.entryconfigure(self.find_menu, state=DISABLED)
        self.findmenu.entryconfigure(self.find_next_menu, state=DISABLED)
        self.findmenu.entryconfigure(self.find_prev_menu, state=DISABLED)
        # Now fill tree with new contents
        for l0, this_box in enumerate(self.mp4file.child_boxes):
            self.treenodes.append(self.tree.insert('', 'end', str(l0), text=str(l0) + " " + this_box.type, open=TRUE))
            for l1, this_box in enumerate(this_box.child_boxes):
                l1_iid = "{0}.{1}".format(l0, l1)
                self.treenodes.append(self.tree.insert(str(l0), 'end', l1_iid, text=l1_iid + " " + this_box.type, open=TRUE))
                for l2, this_box in enumerate(this_box.child_boxes):
                    l2_iid = "{0}.{1}.{2}".format(l0, l1, l2)
                    self.treenodes.append(self.tree.insert(l1_iid, 'end', l2_iid, text=l2_iid + " " + this_box.type, open=TRUE))
                    for l3, this_box in enumerate(this_box.child_boxes):
                        l3_iid = "{0}.{1}.{2}.{3}".format(l0, l1, l2, l3)
                        self.treenodes.append(self.tree.insert(l2_iid, 'end', l3_iid, text=l3_iid + " " + this_box.type, open=TRUE))
                        for l4, this_box in enumerate(this_box.child_boxes):
                            l4_iid = "{0}.{1}.{2}.{3}.{4}".format(l0, l1, l2, l3, l4)
                            self.treenodes.append(self.tree.insert(l3_iid, 'end', l4_iid, text=l4_iid + " " + this_box.type, open=TRUE))
                            for l5, this_box in enumerate(this_box.child_boxes):
                                l5_iid = "{0}.{1}.{2}.{3}.{4}.{5}".format(l0, l1, l2, l3, l4, l5)
                                self.treenodes.append(self.tree.insert(l4_iid, 'end', l5_iid, text=l5_iid + " " + this_box.type, open=TRUE))
                                for l6, this_box in enumerate(this_box.child_boxes):
                                    l6_iid = "{0}.{1}.{2}.{3}.{4}.{5}.{6}".format(l0, l1, l2, l3, l4, l5, l6)
                                    self.treenodes.append(self.tree.insert(l5_iid, 'end', l6_iid, text=l6_iid + " " + this_box.type,
                                                     open=TRUE))
                                    for l7, this_box in enumerate(this_box.child_boxes):
                                        l7_iid = "{0}.{1}.{2}.{3}.{4}.{5}.{6}.{7}".format(l0, l1, l2, l3, l4, l5, l6,
                                                                                          l7)
                                        self.treenodes.append(self.tree.insert(l6_iid, 'end', l7_iid, text=l7_iid + " " + this_box.type,
                                                         open=TRUE))
        logging.debug("Finished populating " + filename)
        self.statustext.set("")
        if self.treenodes:
            self.findmenu.entryconfigure(self.find_menu, state=NORMAL)
            self.findmenu.entryconfigure(self.find_next_menu, state=NORMAL)
            self.findmenu.entryconfigure(self.find_prev_menu, state=NORMAL)

    def find(self, box_name, nodes, title="Find", msg=""):
        current = self.tree.focus()
        if not current:
            current = nodes[0]

        search_now = True
        while search_now:
            start = nodes.index(current) + 1
            if start < len(nodes) - 1:
                for boxid in nodes[start:]:
                    node = self.tree.item(boxid)
                    if node['text'].find(box_name) != -1:
                        self.tree.focus(boxid)
                        self.tree.selection_set(boxid)
                        self.select_box(None)
                        return

            search_now = messagebox.askokcancel(title, msg)
            if search_now:
                current = nodes[0]

    def find_box(self, event=None):
        box_name = simpledialog.askstring(title="Find Box",
                                  prompt="Box Name(case sensitive):")
        if box_name:
            self.find_box_name = box_name
        else:
            return
        if self.treenodes:
            self.find(self.find_box_name, self.treenodes, msg="Can't find box named '" + self.find_box_name + "'\n Search from top?")

    def find_next_box(self, event=None):
        if not self.find_box_name:
            return

        if self.find_box_name and self.treenodes:
            self.find(self.find_box_name, self.treenodes, title="Find Next", msg="Can't find box named '" + self.find_box_name + "'\n Search from top?")

    def find_prev_box(self, event=None):
        if not self.find_box_name:
            return

        if self.find_box_name and self.treenodes:
            treenodes = self.treenodes[::-1]
            self.find(self.find_box_name, treenodes, title="Find Next", msg="Can't find box named '" + self.find_box_name + "'\n Search from bottom?")

    def select_box(self, a):
        """ Callback on selecting an Mp4 box in treeview """
        logging.debug("Box selected " + self.tree.focus())
        self.statustext.set("Loading...")
        self.update_idletasks()
        # self.tree.focus() returns id in the form  n.n.n as text
        l = []
        try:
            l = [int(i) for i in self.tree.focus().split('.')]
        except:
            print(self.tree.focus().split('.'))
            traceback.print_exc(file=sys.stdout)
        box_selected = None
        if len(l) == 1:
            box_selected = self.mp4file.child_boxes[l[0]]
        elif len(l) == 2:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]]
        elif len(l) == 3:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]]
        elif len(l) == 4:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]].child_boxes[l[3]]
        elif len(l) == 5:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]].child_boxes[
                l[3]].child_boxes[l[4]]
        elif len(l) == 6:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]].child_boxes[
                l[3]].child_boxes[l[4]].child_boxes[l[5]]
        elif len(l) == 7:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]].child_boxes[
                l[3]].child_boxes[l[4]].child_boxes[l[5]].child_boxes[l[6]]
        elif len(l) == 8:
            box_selected = self.mp4file.child_boxes[l[0]].child_boxes[l[1]].child_boxes[l[2]].child_boxes[
                l[3]].child_boxes[l[4]].child_boxes[l[5]].child_boxes[l[6]].child_boxes[l[7]]
        logging.debug("Populating text widgets")
        self.populate_text_widget(box_selected)
        logging.debug("Upper text widget populated")
        self.populate_hex_text_widget(box_selected)
        logging.debug("Hex text widget populated")
        self.statustext.set("")

    def populate_text_widget(self, box_selected):
        self.t.delete(1.0, END)
        my_string = "Box is located at position " + "{0:#d}".format(box_selected.start_of_box) + \
                    " from start of from file\n\n"
        hdr_str = json.dumps(box_selected.header.get_header())
        if -1 == hdr_str.find('"IsTruncated": true'):
            my_string += "Has header:\n" + hdr_str + "\n\n"
        else:
            self.t.insert(END, my_string + "Has header:\n")
            self.t.insert(END, hdr_str + "\n\n", 'error')
            my_string = ''
        if len(box_selected.box_info) > 0:
            # insertion order is preserved in modern Python
            my_string += "Has values:\n" + json.dumps(box_selected.box_info, indent=4) + "\n\n"
        if len(box_selected.child_boxes) > 0:
            my_string += "Has child boxes:\n" + json.dumps([box.type for box in box_selected.child_boxes])
        self.t.insert(END, my_string)

    def populate_hex_text_widget(self, box_selected):
        bytes_per_line = 32  # Num bytes per line
        trunc_size = 8192  # Arbitrary max number of bytes to display in hex view to prevent tk text widget barfing.
        self.thex.delete(1.0, END)
        my_byte_string = box_selected.get_bytes()
        trunc = False
        if len(my_byte_string) > trunc_size:
            my_byte_string = my_byte_string[:trunc_size]
            trunc = True
        hex_string = ' Offset  00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18 19 1A 1B 1C 1D 1E 1F\n'
        logging.debug("Hex text beginning")
        offset = 0
        for i in range(0, len(my_byte_string), bytes_per_line):
            byte_line = my_byte_string[i:i + bytes_per_line]
            # which is better 256 or 65536? Maybe 65536 for east asian subs
            char_line = "".join([k if k.isprintable() and ord(k) < 65536 else '.'
                                 for k in byte_line.decode('utf-8', "replace")])
            hex_line = binascii.b2a_hex(byte_line).decode('utf-8')
            pretty_hex_line = " ".join([hex_line[j:j + 2] for j in range(0, len(hex_line), 2)])
            pretty_hex_line = pretty_hex_line.ljust(3 * bytes_per_line)
            hex_string += "{:08X} ".format(offset) + pretty_hex_line + '\t' + char_line + '\n'
            offset += bytes_per_line
        logging.debug("Hex text processed")
        if trunc:
            self.thex.insert(END, 'Hex view, showing first 1MB: \n' + hex_string)
        else:
            self.thex.insert(END, 'Hex view: \n' + hex_string)


if __name__ == '__main__':
    myapp = MyApp()
    myapp.mainloop()
