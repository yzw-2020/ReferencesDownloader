import hashlib
import re
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import requests
import threadpool
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTText
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage


def get_pages(filename, password='', page_numbers=None, maxpages=0, caching=True, laparams=None, reverse=False):
    if not isinstance(laparams, LAParams):
        laparams = LAParams()
    with open(filename, "rb") as fp:
        resource_manager = PDFResourceManager(caching=caching)
        device = PDFPageAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)
        pages = PDFPage.get_pages(
            fp, page_numbers, maxpages=maxpages, password=password, caching=caching)
        if reverse:
            pages = reversed(list(pages))
        for page in pages:
            interpreter.process_page(page)
            yield device.get_result()


class ReferencesDownloader:
    api_url = "https://dblp.org/search/publ/api?q={}&h=1000&format=bib1&rd=1a"

    def __init__(self, caching=True):
        self.caching = caching
        if caching:
            self.refs_dict = {}

        self.pool = threadpool.ThreadPool(16)
        self.session = requests.session()

    def _get_refs(self, filename, password='', page_numbers=None, maxpages=0, caching=True, laparams=None):
        result = []
        # 逆序读取元素，直到遇到References
        for page in get_pages(filename, password=password, page_numbers=page_numbers, maxpages=maxpages, caching=caching, laparams=laparams, reverse=True):
            elems = [elem for elem in page if isinstance(elem, LTText)]
            for elem in elems[-2::-1]:
                string = elem.get_text()
                if re.match(r'^references\n', string.lower()):
                    return self.merge_refs(result)
                for s in reversed(string.strip('\n ').replace('-\n', '').split('\n')):
                    result.append(s.strip())

    def merge_refs(self, res):
        refs = []
        for i in reversed(res):
            if re.match(r"^\[[0-9]+]", i):
                refs.append(i)
            elif refs:
                refs[-1] += ' ' + i
        return refs

    def get_refs(self, filename, password='', page_numbers=None, maxpages=0, caching=True, laparams=None):
        if self.caching and filename in self.refs_dict:
            for ref in self.refs_dict[filename]:
                yield ref
            return

        self.refs = self._get_refs(filename, password, page_numbers,maxpages, caching, laparams)        
        if not self.refs:
            raise Exception("References not found")
        if self.caching:
            self.refs_dict[filename] = self.refs
        for ref in self.refs:
            yield ref

    def modify_refs(self):
        for i in self.refs:
            #     if re.match(r"(http|https)://[\w/]+ ", ref):
            pass

    def get_bib(self, *keywords):
        response = self.se.get(self.api_url.format('+'.join(keywords)))
        
    def clean_cache(self):
        self.refs_dict.clear()


class MY_GUI():
    def __init__(self, window: tk.Tk):
        self.References_Downloader = ReferencesDownloader()
        self.window = window

        self.window.title("References Downloader")
        self.window.geometry("1280x720+40+40")
        # self.window.resizable(False, False)
        self.window["bg"] = "#EEEEEE"
        self.window.attributes("-alpha", 1)
        # 菜单栏
        self.init_menu()
        
        # 文件选择栏
        self.files_label = tk.Label(self.window, text="Files")
        self.files_label.place(relx=0.01, y=0)
        self.files_box = tk.Listbox(self.window, selectmode="single")
        self.files_box.place(relx=0.01, rely=0.03, relheight=0.67, relwidth=0.34)
        
        # 日志栏
        self.log_label = tk.Label(self.window, text="log")
        self.log_label.place(relx=0.01, rely=0.7)
        self.log_box = tk.Listbox(self.window, selectmode="single")
        self.log_box.place(relx=0.01, rely=0.73, relheight=0.22, relwidth=0.34)
        
        # 结果
        self.result_label = tk.Label(self.window, text="Result")
        self.result_label.place(relx=0.55, y=0)
        self.result_box = tk.Listbox(self.window, selectmode="single")
        self.result_box.place(relx=0.45,rely=0.03,relheight=0.92,relwidth=0.54)


        # 功能按钮
        self.analyze_button = tk.Button(self.window, text="Analyze", width=10, command=self.analyze)
        self.analyze_button.place(relx=0.36, rely=0.1, relwidth=0.08)
        self.show_button = tk.Button(self.window, text="Clean", width=10, command=self.clean)
        self.show_button.place(relx=0.36,rely=0.2, relwidth=0.08)
        self.download_button = tk.Button(self.window, text="Download", width=10, command=self.download)
        self.download_button.place(relx=0.36, rely=0.3, relwidth=0.08)
        self.remove_button = tk.Button(self.window, text="Remove", width=10, command=self.remove)
        self.remove_button.place(relx=0.36, rely=0.4, relwidth=0.08)
        self.save_button = tk.Button(self.window, text="Save", width=10, command=self.save)
        self.save_button.place(relx=0.36, rely=0.5, relwidth=0.08)

    def init_menu(self):
        self.menu = tk.Menu(self.window)
        self.menu_f = tk.Menu(self.menu, tearoff=False)
        self.menu_f.add_command(label="Open File", command=self.open_file)
        self.menu_f.add_command(label="Open Files", command=self.open_files)
        self.menu_f.add_command(label="Exit", command=self.window.quit)
        self.menu.add_cascade(label="File", menu=self.menu_f)
        self.menu.add_command(label="Help", command=self.help)
        self.window["menu"] = self.menu

    def help(self):
        msg = "help"
        messagebox.showinfo(title="Help", message=msg)

    def open_file(self):
        file = filedialog.askopenfilename()
        if file and file not in self.files_box.get(0,"end"):
            self.files_box.insert("end", file)

    def open_files(self):
        files = filedialog.askopenfilenames()
        for file in files:
            if file not in self.files_box.get(0,"end"):
                self.files_box.insert("end", file)

    def analyze(self):
        index = self.files_box.curselection()
        if not index:
            return
        filename = self.files_box.get(index[0])
        try:
            refs = self.References_Downloader.get_refs(filename)
        except Exception as e:
            messagebox.showerror("Error",str(e))
            return self.log_box.insert("end", "%s %s Analyze Failed" %(self.get_str_time(),filename))
        try:
            self.result_box.delete(0,"end")
        except:
            pass
        self.result_box.insert("end",*refs)
        self.log_box.insert("end",  "%s %s Analyze Successed" %(self.get_str_time(),filename))
        
    def clean(self):
        self.References_Downloader.clean_cache()
        self.log_box.insert("end", self.get_str_time()+" Cache Cleaned")

    def get_str_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def download(self):
        pass

    def remove(self):
        index = self.files_box.curselection()
        if index:
            filename = self.files_box.get(index[0])
            self.files_box.delete(index[0])
            self.log_box.insert("end",  "%s %s Removed" %(self.get_str_time(),filename))
    
    def save(self):
        pass

    def run(self):
        self.window.mainloop()
