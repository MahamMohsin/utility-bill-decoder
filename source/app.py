"""Optional native desktop frontend; all inference uses the shared gateway."""
import argparse
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageOps, ImageTk
from extractor import extract
from model_client import Client, ROOT
from question_answering import answer_questions

class App:
    def __init__(self,window):
        self.window=window
        self.events=queue.Queue()
        self.result=None
        self.client=None
        window.title('Women Tech Quest | Utility Bill Decoder')
        width=min(980,max(640,window.winfo_screenwidth()-100))
        height=min(650,max(450,window.winfo_screenheight()-160))
        window.geometry(f'{width}x{height}')
        window.minsize(640,450)
        window.columnconfigure(0,weight=1)
        window.rowconfigure(2,weight=1)
        window.configure(bg='#f4f2ec')
        style=ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame',background='#f4f2ec')
        style.configure('TLabel',background='#f4f2ec',foreground='#173e3d',font=('Segoe UI',11))
        style.configure('TButton',font=('Segoe UI',11),padding=8)
        header=ttk.Frame(window,padding=12)
        header.grid(row=0,column=0,sticky='ew')
        ttk.Label(header,text='Utility Bill Decoder',font=('Segoe UI',20,'bold')).pack(side='left')
        self.choose=ttk.Button(header,text='Select bill image',command=self.select)
        self.choose.pack(side='right')
        self.status=tk.StringVar(value='Select a PNG or JPG bill to get started.')
        ttk.Label(window,textvariable=self.status,padding=(12,0,12,8)).grid(row=1,column=0,sticky='ew')
        body=ttk.Frame(window,padding=(12,0))
        body.grid(row=2,column=0,sticky='nsew')
        body.columnconfigure(0,weight=1)
        body.columnconfigure(1,weight=1)
        body.rowconfigure(1,weight=1)
        ttk.Label(body,text='YOUR BILL',font=('Segoe UI',10,'bold')).grid(row=0,column=0,sticky='w',pady=8)
        ttk.Label(body,text='EXTRACTED BILL DETAILS',font=('Segoe UI',10,'bold')).grid(row=0,column=1,sticky='w',pady=8)
        self.preview=tk.Label(body,bg='white',text='Bill preview',fg='#173e3d',width=1,height=1)
        self.original_preview=None
        self.preview.bind('<Configure>',self.resize_preview)
        self.preview.grid(row=1,column=0,sticky='nsew',padx=(0,16))
        self.json=ScrolledText(body,font=('Consolas',10),wrap='word',width=30,height=1,bg='white')
        self.json.grid(row=1,column=1,sticky='nsew')
        bottom=ttk.Frame(window,padding=12)
        bottom.grid(row=3,column=0,sticky='ew')
        ttk.Label(bottom,text='Ask about this bill').pack(anchor='w',pady=(0,6))
        row=ttk.Frame(bottom)
        row.pack(fill='x')
        self.question=ttk.Entry(row,font=('Segoe UI',12))
        self.question.pack(side='left',fill='x',expand=True,padx=(0,12))
        self.question.bind('<Return>',lambda event:self.ask())
        self.ask_button=ttk.Button(row,text='Ask question',command=self.ask,state='disabled')
        self.ask_button.pack(side='right')
        self.answer=ScrolledText(bottom,height=4,wrap='word',font=('Segoe UI',11),bg='white')
        self.answer.pack(fill='x',pady=(12,0))
        self.json.configure(state='disabled')
        self.answer.configure(state='disabled')
        window.after(100,self.poll)

    @staticmethod
    def show(widget,text):
        widget.configure(state='normal')
        widget.delete('1.0','end')
        widget.insert('1.0',text)
        widget.configure(state='disabled')

    def busy(self,text):
        self.status.set(text)
        self.choose.configure(state='disabled')
        self.ask_button.configure(state='disabled')

    def select(self):
        filename=filedialog.askopenfilename(title='Select electricity bill',
                    filetypes=[('Bill images','*.png *.jpg *.jpeg')])
        if filename:
            self.load(Path(filename))

    def load(self,path):
        try:
            with Image.open(path) as original:
                self.original_preview=ImageOps.exif_transpose(original).convert('RGB')
            self.resize_preview()
        except Exception:
            self.status.set('Cannot open this image. Please select a valid PNG or JPG.')
            return
        self.result=None
        self.show(self.json,'Reading this bill...')
        self.show(self.answer,'')
        self.busy('Extracting printed bill details...')
        def work():
            self.client=self.client or Client()
            return extract(self.client,path,ROOT/'cache')
        self.start('extract',work)

    def resize_preview(self,event=None):
        if self.original_preview is None:
            return
        preview=self.original_preview.copy()
        preview.thumbnail((max(1,self.preview.winfo_width()-8),
                           max(1,self.preview.winfo_height()-8)))
        self.photo=ImageTk.PhotoImage(preview)
        self.preview.configure(image=self.photo,text='')

    def start(self,kind,work):
        def worker():
            try:
                self.events.put((kind,work()))
            except Exception as error:
                # No provider exception bodies or credentials are exposed in the UI.
                self.events.put(('error',type(error).__name__))
        threading.Thread(target=worker,daemon=True).start()

    def ask(self):
        question=self.question.get().strip()
        if not question or self.result is None or str(self.ask_button['state'])=='disabled':
            return
        self.busy('Checking bill evidence and calculating the answer...')
        self.start('answer',lambda:answer_questions(self.client,self.result,
                   [{'question_id':'user','question':question}],ROOT/'cache')['user'])

    def poll(self):
        try:
            kind,value=self.events.get_nowait()
            if kind=='extract':
                self.result=value
                self.show(self.json,json.dumps(value.bill.model_dump(),indent=2))
                self.status.set('Bill extracted. Ask a question below.')
                self.question.focus_set()
            elif kind=='answer':
                self.show(self.answer,value)
                self.status.set('Answer ready.')
            else:
                self.status.set(f'Processing failed ({value}). Check .env and API availability, then retry.')
            self.choose.configure(state='normal')
            self.ask_button.configure(state='normal' if self.result is not None else 'disabled')
        except queue.Empty:
            pass
        self.window.after(100,self.poll)

def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true',help='Check desktop widget creation without API calls')
    args=parser.parse_args()
    window=tk.Tk()
    if args.self_test:
        window.withdraw()
    app=App(window)
    if args.self_test:
        app.show(app.answer,'UI test')
        assert app.answer.get('1.0','end').strip()=='UI test'
        assert str(app.ask_button['state'])=='disabled'
        # Exercise actual geometry after loading a bill, without network inference.
        app.start=lambda kind,work:None
        bill=next((ROOT/'train'/'bills').rglob('KESC_0008.png'),None)
        window.geometry('640x450+-10000+-10000')
        window.deiconify()
        window.update_idletasks()
        if bill:
            app.load(bill)
        for width,height in ((640,450),(800,600),(980,650)):
            window.geometry(f'{width}x{height}+-10000+-10000')
            window.update()
            for widget in (app.question,app.ask_button,app.answer):
                top=widget.winfo_rooty()-window.winfo_rooty()
                assert top>=0 and top+widget.winfo_height()<=window.winfo_height(), 'Question controls clipped'
        window.destroy()
        print('Desktop UI check passed: loaded bill; question controls visible at 640x450, 800x600, 980x650')
    else:
        window.mainloop()

if __name__=='__main__':
    cli()
