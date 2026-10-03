"""Resident window and owned proxy lifecycle. Launch using this project's pythonw."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import tkinter as tk
import tempfile
from pathlib import Path
from tkinter import messagebox, ttk

import certifi
import psutil
from mitmproxy.certs import CertStore

from live_store import Store, verdict

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local'


def prepare_ca():
    directory = LOCAL / 'ca'
    directory.mkdir(parents=True, exist_ok=True)
    CertStore.from_store(directory, 'mitmproxy', 2048)
    bundle = LOCAL / 'codex-ca-bundle.pem'
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b'\n' +
                       (directory / 'mitmproxy-ca-cert.pem').read_bytes())
    return bundle


def available(port):
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1', port)) == 0


class Monitor:
    def __init__(self, launch=False, demo=False):
        LOCAL.mkdir(exist_ok=True)
        self.demo = demo
        self.demo_directory = tempfile.TemporaryDirectory() if demo else None
        self.store = Store(Path(self.demo_directory.name) / 'demo.sqlite') if demo else Store()
        self.proxy = None
        self.launch_process = None
        self.launch_result = LOCAL / 'launch-result.json'
        self.last_seen = time.time()
        self.root = tk.Tk()
        self.root.title('Codex · 模型观察窗（演示）' if demo else 'Codex · 模型观察窗')
        self.root.geometry('720x460')
        self.root.minsize(620, 370)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='#f3f7f7')
        self.root.protocol('WM_DELETE_WINDOW', self.root.iconify)
        self.state = tk.StringVar(value='正在启动本地采集器…')
        self.details = tk.StringVar(value='等待通过联动入口启动的 Codex 请求。')
        self.auto_show = tk.BooleanVar(value=True)
        self.topmost = tk.BooleanVar(value=True)
        bar = ttk.Frame(self.root, padding=14)
        bar.pack(fill='x')
        ttk.Label(bar, text='请求模型 / 响应模型', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(bar, textvariable=self.state, wraplength=680).pack(anchor='w', pady=7)
        ttk.Label(bar, textvariable=self.details, wraplength=680).pack(anchor='w')
        self.table = ttk.Treeview(self.root, columns=('time', 'request', 'response', 'result'), show='headings', height=9)
        for key, label, width in [('time', '时间', 75), ('request', '请求模型', 180), ('response', '响应声明模型', 180), ('result', '状态', 145)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=50)
        self.table.pack(fill='both', expand=True, padx=14)
        self.table.bind('<<TreeviewSelect>>', self.select)
        controls = ttk.Frame(self.root, padding=12)
        controls.pack(fill='x')
        ttk.Checkbutton(controls, text='新事件显示窗口', variable=self.auto_show).pack(side='left')
        ttk.Checkbutton(controls, text='置顶', variable=self.topmost,
                        command=lambda: self.root.attributes('-topmost', self.topmost.get())).pack(side='left')
        ttk.Button(controls, text='启动 Codex', command=self.launch,
                   state='disabled' if demo else 'normal').pack(side='right', padx=4)
        ttk.Button(controls, text='停止并退出', command=self.quit).pack(side='right', padx=4)
        ttk.Label(self.root, text='模型名称来自流量字段；名称一致不证明底层模型身份。关闭按钮仅最小化。',
                  wraplength=680).pack(padx=14, pady=(0, 12), anchor='w')
        self.rows = {}
        if demo:
            from capture_core import Capture
            self.demo_capture = Capture(self.store)
            self.state.set('演示模式 · 测试数据 · 不连接 Codex、不启动代理')
            self.root.after(1000, lambda: self.demo_capture.request('demo',
                {'type': 'response.create', 'model': 'demo-model'}, 'websocket'))
            self.root.after(2500, lambda: self.demo_capture.response('demo',
                {'type': 'response.completed', 'response': {'id': 'resp_demo', 'model': 'demo-model'}}))
        else:
            self.start_proxy()
        if launch and not demo:
            self.root.after(700, self.launch)
        self.root.after(500, self.poll)

    def start_proxy(self):
        if available(8901):
            self.state.set('8901 端口已占用，未启动采集。请检查其他实例。')
            return
        prepare_ca()
        args = [str(ROOT / '.venv/Scripts/mitmdump.exe'), '-q', '-s', str(ROOT / 'capture_addon.py'),
                '--listen-host', '127.0.0.1', '--listen-port', '8901',
                '--set', f'confdir={LOCAL / "ca"}', '--set', 'flow_detail=0',
                '--set', 'allow_hosts=^(chatgpt\\.com|api\\.openai\\.com)(:443)?$']
        if available(7897):
            args += ['--mode', 'upstream:http://127.0.0.1:7897']
        self.proxy = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        (LOCAL / 'proxy.pid').write_text(str(self.proxy.pid))

    def launch(self):
        if not self.proxy or self.proxy.poll() is not None or not available(8901):
            self.state.set('采集器尚未就绪，未启动 Codex。')
            return
        if self.launch_process and self.launch_process.poll() is None:
            return
        self.launch_result.unlink(missing_ok=True)
        script = ROOT / 'launch-desktop.ps1'
        self.launch_process = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                                '-File', str(script)], cwd=ROOT, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        self.state.set('正在准备联动启动…')

    def select(self, _=None):
        selection = self.table.selection()
        if selection and selection[0] in self.rows:
            row = self.rows[selection[0]]
            self.details.set(f"任务 {row.get('thread_id') or '未提供'} · 轮次 {row.get('turn_id') or '未提供'}\n"
                             f"响应 {row.get('response_id') or '等待'} · {row.get('transport')} · {row.get('status')}")

    def poll(self):
        try:
            if self.proxy and self.proxy.poll() is not None:
                self.state.set('采集器已停止。正在运行的监测版 Codex 可能无法发送请求，请普通重启或重开观察窗。')
            elif self.launch_process and self.launch_process.poll() is not None:
                if self.launch_result.exists():
                    result = json.loads(self.launch_result.read_text(encoding='utf-8-sig'))
                    self.state.set(result.get('message', '启动结果未知'))
                else:
                    self.state.set('启动脚本未返回结果，请检查 launch-desktop.ps1。')
                self.launch_process = None
            elif self.state.get().startswith('正在启动') and available(8901):
                self.state.set('采集器就绪 · 127.0.0.1:8901 · 仅监测通过联动入口启动的 Codex')
            if not self.demo and self.proxy and self.proxy.poll() is None and time.time() > getattr(self, 'next_health', 0):
                self.next_health = time.time() + 5
                desktop = []
                for process in psutil.process_iter(['pid', 'name', 'ppid']):
                    if (process.info['name'] or '').lower() == 'chatgpt.exe':
                        desktop.append(process)
                pids = {process.pid for process in desktop}
                main_processes = [process for process in desktop if process.ppid() not in pids]
                if main_processes:
                    enabled = any(process.environ().get('HTTPS_PROXY') == 'http://127.0.0.1:8901' and
                                  process.environ().get('CODEX_CA_CERTIFICATE') == str(LOCAL / 'codex-ca-bundle.pem')
                                  for process in main_processes)
                    self.state.set('Codex 已通过监测入口启动 · 等待/观察响应' if enabled else
                                   '当前 Codex 未使用监测设置。请完全退出后从 Model Monitor 入口重开。')
                else:
                    self.state.set('采集器就绪 · 点击“启动 Codex”或使用桌面 Model Monitor 入口')
            rows = self.store.recent(30)
            signature = [(r['id'], r['updated']) for r in rows]
            if signature != getattr(self, 'signature', None):
                selection = self.table.selection()
                self.signature = signature
                self.rows = {r['id']: r for r in rows}
                self.table.delete(*self.table.get_children())
                for row in rows:
                    self.table.insert('', 'end', iid=row['id'], values=(time.strftime('%H:%M:%S', time.localtime(row['started'])),
                        row.get('request_model') or '未提供', row.get('response_model') or '未提供', verdict(row)))
                if selection and selection[0] in self.rows:
                    self.table.selection_set(selection[0])
                if rows and rows[0]['updated'] > self.last_seen:
                    self.last_seen = rows[0]['updated']
                    latest = rows[0]
                    self.details.set(f"{latest.get('request_model') or '未提供'} → {latest.get('response_model') or '未提供'} · {verdict(latest)}")
                    if self.auto_show.get():
                        self.root.deiconify()
            while lock is not None:
                try:
                    client, _ = lock.accept()
                except BlockingIOError:
                    break
                with client:
                    client.settimeout(.2)
                    command = client.recv(32)
                self.root.deiconify()
                if command == b'launch':
                    self.launch()
        except Exception:
            self.state.set('观察窗读取失败；采集进程状态请检查。')
        self.root.after(500, self.poll)

    def quit(self):
        if not self.demo and not messagebox.askyesno('停止采集', '停止代理后，监测版 Codex 需要关闭并用普通入口重开才能恢复直连。确认停止？'):
            return
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self.proxy and self.proxy.poll() is None:
                self.proxy.terminate()
                try:
                    self.proxy.wait(5)
                except subprocess.TimeoutExpired:
                    self.proxy.kill()
                    self.proxy.wait(5)
            if self.demo_directory:
                self.demo_directory.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--demo', action='store_true', help='Show an isolated synthetic request/response demo')
    args = parser.parse_args()
    lock = None
    if not args.demo:
        lock = socket.socket()
        try:
            lock.bind(('127.0.0.1', 8902))
        except OSError:
            with socket.create_connection(('127.0.0.1', 8902), timeout=1) as existing:
                existing.sendall(b'launch' if args.launch else b'show')
            sys.exit(0)
        lock.listen(4)
        lock.setblocking(False)
    try:
        Monitor(args.launch, args.demo).run()
    finally:
        if lock:
            lock.close()
