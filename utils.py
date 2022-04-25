import asyncio
import hashlib
import re
import tkinter as tk
from datetime import datetime
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
    api_url = "https://dblp.org/search/publ/api?q={}&h=5&format=bib1&rd=1a"

    def __init__(self, caching=True):
        self.caching = caching
        if caching:
            self.refs_dict = {}


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
        self.modify_refs()
        if not self.refs:
            raise Exception("References not found")
        if self.caching:
            self.refs_dict[filename] = self.refs
        for ref in self.refs.copy():
            yield ref


    def modify_refs(self):
        for i,ref in enumerate(self.refs):
            self.refs[i] = re.sub(r".[0-9,， ]+$",".",ref)


    def ref_to_keys(self, ref):
        return [i.strip() for i in re.sub(r"^\[[0-9]+]", "", ref).strip(' .').split('.')]



    def get_bib(self, *keywords):
        keywords = [key.replace(" ","+") for key in keywords]
        response = requests.get(self.api_url.format('+'.join(keywords)))
        if response.text:
                return response
        keywords.pop()
        response = requests.get(self.api_url.format('+'.join(keywords)))
        if response.text:
                return response
        keywords = "+".join(keywords).split("+")
        while True:
            if keywords:
                keywords.pop()
            else:
                return
            if len(keywords)<4:
                return
            response = requests.get(self.api_url.format('+'.join(keywords)))
            retry = 0
            while response.status_code != 200:
                response = requests.get(self.api_url.format('+'.join(keywords)))
                retry += 1
                if retry > 3:
                    response.text = "Server Error! Code:" + str(response.status_code)
                    break         
            if response.text:
                return response


    def clean_cache(self):
        self.refs_dict.clear()


class MY_GUI():
    def __init__(self, window: tk.Tk):
        self.References_Downloader = ReferencesDownloader()
        self.cache = {}
        self.bib_result = {}
        self.pool = threadpool.ThreadPool(16)
        self.window = window


        self.window.title("References Downloader")
        self.window.geometry("1280x720+40+40")
        self.window.resizable(False, False)
        self.window["bg"] = "#EEEEEE"
        self.window.attributes("-alpha", 1)
        # 菜单栏
        self.menu = tk.Menu(self.window)
        self.menu_f = tk.Menu(self.menu, tearoff=False)
        self.menu_f.add_command(label="Open File", command=self.open_file)
        self.menu_f.add_command(label="Open Files", command=self.open_files)
        self.menu_f.add_command(label="Exit", command=self.window.quit)
        self.menu.add_cascade(label="File", menu=self.menu_f)
        self.menu.add_command(label="Help", command=self.help)
        self.window["menu"] = self.menu

        # 文件选择栏
        self.files_label = tk.Label(self.window, text="Files")
        self.files_label.place(relx=0.01, y=0)
        self.frame_files = tk.Frame(self.window)
        self.frame_files.place(relx=0.01, rely=0.03, relheight=0.67, relwidth=0.34)
        self.files_box = tk.Listbox(self.frame_files, selectmode="single")
        self.files_box.place(relx=0, rely=0, relheight=0.96, relwidth=0.95)
        self.files_box.bind("<Double-Button-1>", lambda event: self.refresh())
        self.files_scroll_bar_x = tk.Scrollbar(self.frame_files, orient="horizontal", command=self.files_box.xview)
        self.files_scroll_bar_x.place(relx=0, rely=0.96, relheight=0.04, relwidth=1)
        self.files_box.config(xscrollcommand=self.files_scroll_bar_x.set)
        self.files_scroll_bar_y = tk.Scrollbar(self.frame_files, orient="vertical", command=self.files_box.yview)
        self.files_scroll_bar_y.place(relx=0.95, rely=0, relheight=1, relwidth=0.05)
        self.files_box.config(yscrollcommand=self.files_scroll_bar_y.set)
        # 日志栏
        self.log_label = tk.Label(self.window, text="log")
        self.log_label.place(relx=0.01, rely=0.7)
        self.frame_log = tk.Frame(self.window)
        self.frame_log.place(relx=0.01, rely=0.73, relheight=0.26, relwidth=0.44)
        self.log_box = tk.Listbox(self.frame_log, selectmode="single")
        self.log_box.place(relx=0, rely=0, relheight=0.88, relwidth=0.95)
        self.log_scroll_bar_x = tk.Scrollbar(self.frame_log, orient="horizontal", command=self.log_box.xview)
        self.log_scroll_bar_x.place(relx=0, rely=0.88, relheight=0.12, relwidth=1)
        self.log_box.config(xscrollcommand=self.log_scroll_bar_x.set)
        self.log_scroll_bar_y = tk.Scrollbar(self.frame_log, orient="vertical", command=self.log_box.yview)
        self.log_scroll_bar_y.place(relx=0.95, rely=0, relheight=1, relwidth=0.05)
        self.log_box.config(yscrollcommand=self.log_scroll_bar_y.set)
        # 参考文献
        self.references_label = tk.Label(self.window, text="References")
        self.references_label.place(relx=0.45, y=0)
        self.frame_references = tk.Frame(self.window)
        self.frame_references.place(relx=0.45 ,rely=0.03, relheight=0.96, relwidth=0.54)
        self.references_box = tk.Listbox(self.frame_references, selectmode="single")
        self.references_box.place(relx=0 ,rely=0, relheight=0.97, relwidth=0.97)
        self.references_scroll_bar_x = tk.Scrollbar(self.frame_references, orient="horizontal", command=self.references_box.xview)
        self.references_scroll_bar_x.place(relx=0, rely=0.97, relheight=0.03, relwidth=1)
        self.references_box.config(xscrollcommand=self.references_scroll_bar_x.set)
        self.references_scroll_bar_y = tk.Scrollbar(self.frame_references, orient="vertical", command=self.references_box.yview)
        self.references_scroll_bar_y.place(relx=0.97, rely=0, relheight=1, relwidth=0.03)
        self.references_box.config(yscrollcommand=self.references_scroll_bar_y.set)
        self.current_show = self.frame_references
        # 结果
        self.result_label = tk.Label(self.window, text="result")
        self.frame_result = tk.Frame(self.window)
        self.result_box = tk.Text(self.frame_result)
        self.result_box.place(relx=0 ,rely=0, relheight=0.97, relwidth=0.97)
        self.result_scroll_bar_x = tk.Scrollbar(self.frame_result, orient="horizontal", command=self.result_box.xview)
        self.result_scroll_bar_x.place(relx=0, rely=0.97, relheight=0.03, relwidth=1)
        self.result_box.config(xscrollcommand=self.result_scroll_bar_x.set)
        self.result_scroll_bar_y = tk.Scrollbar(self.frame_result, orient="vertical", command=self.result_box.yview)
        self.result_scroll_bar_y.place(relx=0.97, rely=0, relheight=1, relwidth=0.03)
        self.result_box.config(yscrollcommand=self.result_scroll_bar_y.set)

        # 功能按钮
        self.analyze_button = tk.Button(self.window, text="Analyze", width=10, command=self.analyze)
        self.analyze_button.place(relx=0.36, rely=0.05, relwidth=0.08)
        self.analyze_all_button = tk.Button(self.window, text="Analyze All", width=10, command=self.analyze_all)
        self.analyze_all_button.place(relx=0.36, rely=0.15, relwidth=0.08)
        self.show_button = tk.Button(self.window, text="Clean", width=10, command=self.clean)
        self.show_button.place(relx=0.36,rely=0.25, relwidth=0.08)
        self.download_button = tk.Button(self.window, text="Download", width=10, command=self.download)
        self.download_button.place(relx=0.36, rely=0.35, relwidth=0.08)
        self.remove_button = tk.Button(self.window, text="Remove", width=10, command=self.remove)
        self.remove_button.place(relx=0.36, rely=0.45, relwidth=0.08)
        self.save_button = tk.Button(self.window, text="Save", width=10, command=self.save)
        self.save_button.place(relx=0.36, rely=0.55, relwidth=0.08)
        self.switch_button = tk.Button(self.window, text="Switch", width=10, command=self.switch)
        self.switch_button.place(relx=0.36, rely=0.65, relwidth=0.08)




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


    def get_active_file(self):
        index = self.files_box.curselection()
        if not index:
            return
        return self.files_box.get(index[0])


    def analyze_all(self):
        for filename in self.files_box.get(0,"end"):
            self.analyze(filename)


    def analyze(self,filename=None):
        if filename is None:
            filename = self.get_active_file()
        if not filename:
            return
        try:
            self.cache[filename] = list(self.References_Downloader.get_refs(filename))
        except Exception as e:
            messagebox.showerror("Error",str(e))
            return self.log(filename + " analyze failed ")
        self.log(filename + " analyze successed ")
        self.refresh()


    def _download(self, filename):
        RD = self.References_Downloader
        def get_bib(ref):
            keys = RD.ref_to_keys(ref)
            bib = RD.get_bib(*keys)
            return ref,bib
        refs = list(RD.get_refs(filename))
        result = {}
        def callback(workrequest,res):
            result[res[0]] = "None" if res[1] is None else res[1].text
        reqs = threadpool.makeRequests(get_bib, refs, callback)
        for req in reqs:
            self.pool.putRequest(req)
        self.pool.wait()
        s = "".join(["%s\n%s\n" %(ref,result[ref]) for ref in refs])
        return s


    def download(self):
        filename = self.get_active_file()
        bibs = self._download(filename)
        self.bib_result[filename] = bibs
        try:
            self.result_box.delete(0, "end")
        except:
            pass
        self.result_box.insert("end", bibs)
        self.log("download successed ")
        return bibs

    def save(self):
        filename = self.get_active_file()
        bibs = self.bib_result.get(filename, None)
        if bibs is None:
            bibs = self.download()


    def remove(self):
        index = self.files_box.curselection()
        if index:
            filename = self.files_box.get(index[0])
            self.files_box.delete(index[0])
            self.log(filename + " removed ")
        self.refresh()


    def clean(self):
        self.References_Downloader.clean_cache()
        self.cache.clear()
        self.bib_result.clear()
        self.log("cache Cleaned ")
        self.refresh()


    def log(self,string: str):
        self.log_box.insert("end", self.get_str_time()+string)
        self.log_box.yview_moveto(1)
    
    def get_str_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S ")


    def refresh(self):
        if getattr(self, "_filename", None) == self.get_active_file():
            return
        else:
            self._filename = self.get_active_file()
        try:
            self.references_box.delete(0, "end")
        except:
            pass
        try:
            self.result_box.delete(0, "end")
        except:
            pass
        self.references_box.insert("end",*self.cache.get(self._filename, []))
        self.result_box.insert("end", self.bib_result.get(self._filename, ""))


    def switch(self):
        if self.current_show == self.frame_references:
            show = self.frame_result
            show_label = self.result_label
            current_show_label = self.references_label
        else:
            show = self.frame_references
            show_label = self.references_label
            current_show_label = self.result_label
        show.place(relx=0.45 ,rely=0.03, relheight=0.96, relwidth=0.54)
        show_label.place(relx=0.45, y=0)
        current_show_label.place_forget()
        self.current_show.place_forget()
        self.current_show = show


    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    GUI = MY_GUI(tk.Tk())
    GUI.run()
