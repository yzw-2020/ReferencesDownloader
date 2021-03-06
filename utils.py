import re
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from functools import wraps
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
                    return self._merge_refs(result)
                for s in reversed(string.strip('\n ').replace('-\n', '').split('\n')):
                    result.append(s.strip())


    def _merge_refs(self, res):
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
        self._modify_refs()
        if not self.refs:
            raise Exception("References not found")
        if self.caching:
            self.refs_dict[filename] = self.refs
        for ref in self.refs.copy():
            yield ref


    def _modify_refs(self):
        for i,ref in enumerate(self.refs):
            self.refs[i] = re.sub(r".[0-9,， ]+$",".",ref)


    def ref_to_keys(self, ref):
        return [i.strip() for i in re.sub(r"^\[[0-9]+]", "", ref).replace(",", " ").strip(' .').split('.')]



    def get_bib(self, *keywords):
        keywords = list(keywords)
        # keywords[0] = re.sub(r"and", " ", keywords[0])
        keywords = [re.sub(r" +", "+", key) for key in keywords]
        response = requests.get(self.api_url.format('+'.join(keywords)))
        if response.text and response.status_code == 200:
                return response.text
        keywords.pop()
        response = requests.get(self.api_url.format('+'.join(keywords)))
        if response.text and response.status_code == 200:
                return response.text
        keywords = "+".join(keywords).split("+")
        while True:
            if keywords:
                for i in range(len(keywords)//10+1):
                    keywords.pop()
            else:
                return
            if len(keywords)<4:
                if response.status_code != 200:
                    return "Server Error! Code:" + str(response.status_code) 
                return
            url = self.api_url.format('+'.join(keywords))
            print(url)
            response = requests.get(url)
            if response.text and response.status_code==200:
                return response.text


    def clean_cache(self):
        self.refs_dict.clear()

def nowait(function):
    """"""
    pool = threadpool.ThreadPool(4)
    @wraps(function)
    def func(self, *args, **kwargs):
        def func1(*args,**kwargs):
            return function(self,*args,**kwargs)
        for i in threadpool.makeRequests(func1,args_list=((args,kwargs),)):
            pool.putRequest(i)
        pool.poll()
    return func

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
        # Menu Bar
        self.menu = tk.Menu(self.window)
        self.menu_f = tk.Menu(self.menu, tearoff=False)
        self.menu_f.add_command(label="Open File", command=self.open_file)
        self.menu_f.add_command(label="Open Files", command=self.open_files)
        self.menu_f.add_command(label="Exit", command=self.window.quit)
        self.menu.add_cascade(label="File", menu=self.menu_f)
        self.menu.add_command(label="Help", command=self.help)
        self.window["menu"] = self.menu
        # File
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
        # Log
        self.log_label = tk.Label(self.window, text="Log")
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
        # References
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
        # Result
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
        # Function Botton
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
        msg = \
        """
        File: Open File -> open single file
        File: Open Files -> open muti files
        File: Exit -> exit program
        Help: show help
        Analyze: analyze selected file, show in references box
        Analyze All: analyze all files, show selected file
        Clean: clean cache
        Download: according to analyzed file, download bib form dblp
        Remove: close selected file, clear references and downloaded result
        Save: save downloaded result into file
        Switch: witch current show content,form references to result or from result to references
        UI: File -> show opened file,double click to switch file to show
        UI: Log -> show logs
        UI: References  > show analyze result
        UI: Result -> show Download result
        """
        messagebox.showinfo(title="Help", message=msg)


    def open_file(self):
        file = filedialog.askopenfilename(filetypes=[("PDF","pdf")])
        if file and file not in self.files_box.get(0,"end"):
            self.files_box.insert("end", file)


    def open_files(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF","pdf")])
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
        self.log(filename + " analyze success ")
        self.refresh()


    def _download(self, filename):
        RD = self.References_Downloader
        def get_bib(ref):
            keys = RD.ref_to_keys(ref)
            bib = RD.get_bib(*keys)
            return ref,bib
        refs = list(RD.get_refs(filename))
        result = {}
        def callback(x,res):
            result[res[0]] = "None" if res[1] is None else res[1]
        reqs = threadpool.makeRequests(get_bib, refs, callback)
        for req in reqs:
            self.pool.putRequest(req)
        self.pool.wait()
        s = "".join(["%s\n%s\n" %(ref,result[ref]) for ref in refs])
        return s

    @nowait
    def download(self):
        filename = self.get_active_file()
        if filename is None:
            return
        self.log("downloading ")
        try:
            bibs = self._download(filename)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log("download failed ")
            return
        self.bib_result[filename] = bibs
        try:
            self.result_box.delete(0, "end")
        except:
            pass
        self.result_box.insert("end", bibs)
        self.log("download success ")

    def save(self):
        filename = self.get_active_file()
        if not filename:
            return messagebox.showinfo("tip", "no file selected")
        bibs = self.bib_result.get(filename, None)
        if bibs is None:
            return messagebox.showinfo("tip", "haven't download")
        savename = re.search(r"/*.", filename).group()[1:] + 'txt'
        file = filedialog.asksaveasfilename(initialdir=".", initialfile=savename,filetypes=[("all","*")])
        with open(file,"w",encoding="utf-8") as f:
            f.write(bibs)
        self.log("save as "+file+" success")            


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
        self.log("cache cleaned ")
        self.refresh()


    def log(self,string: str):
        self.log_box.insert("end", self._get_str_time()+string)
        self.log_box.yview_moveto(1)
    
    def _get_str_time(self):
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
            self.result_box.delete(0.0,"end")
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
