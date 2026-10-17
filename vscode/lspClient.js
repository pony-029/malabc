// lspClient.js —— 手写的最小 LSP 客户端（零 npm 依赖）。
//
// 为什么不用 vscode-languageclient：那要 `npm install`，而本仓的卖点是
// 离线、零依赖、内网可用。协议只有两种帧（请求/通知 + Content-Length），
// 自己写 70 行比拉一个依赖树更符合这个项目的性格。
//
// 这个文件**不 require('vscode')**，所以它能被 `node test_client.js` 直接测。

'use strict';

const { spawn } = require('child_process');

class LspClient {
  constructor(opts) {
    this.python = opts.python || 'python';
    this.script = opts.script;
    this.cwd = opts.cwd || process.cwd();
    this.seq = 0;
    this.pending = new Map();
    this.buf = Buffer.alloc(0);
    this.notificationHandler = null;
    this.stderrTail = [];

    this.proc = spawn(this.python, [this.script], { cwd: this.cwd });
    this.proc.stdout.on('data', (chunk) => this._onData(chunk));
    this.proc.stderr.on('data', (chunk) => {
      this.stderrTail.push(chunk.toString('utf8'));
      if (this.stderrTail.length > 50) this.stderrTail.shift();
    });
    // stdin 的 EPIPE 是**异步事件**，try/catch 抓不到：对端 python 先退出时，
    // 任何一次 write 都会 throw 到进程级（实测把 VSCode 宿主带崩）。
    // 这里吞掉——写失败本身已有 `pending` 的 15s 超时兜底。
    this.proc.stdin.on('error', () => { /* ignore EPIPE */ });
    this.proc.on('error', () => { /* spawn 失败：initialize 的 catch 会报 */ });
  }

  _onData(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    for (;;) {
      const sep = this.buf.indexOf('\r\n\r\n');
      if (sep < 0) return;
      const head = this.buf.slice(0, sep).toString('ascii');
      const m = /content-length:\s*(\d+)/i.exec(head);
      if (!m) { this.buf = this.buf.slice(sep + 4); continue; }
      const len = parseInt(m[1], 10);
      const start = sep + 4;
      if (this.buf.length < start + len) return;
      const body = this.buf.slice(start, start + len).toString('utf8');
      this.buf = this.buf.slice(start + len);
      let msg;
      try { msg = JSON.parse(body); } catch (e) { continue; }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        resolve(msg);
      } else if (msg.method) {
        if (this.notificationHandler) this.notificationHandler(msg);
      }
    }
  }

  _write(obj) {
    if (!this.proc || this.proc.exitCode !== null || this.proc.killed) return;
    const body = Buffer.from(JSON.stringify(obj), 'utf8');
    try {
      this.proc.stdin.write(`Content-Length: ${body.length}\r\n\r\n`);
      this.proc.stdin.write(body);
    } catch (e) {
      // 同步写失败（EPIPE）—— 同上，交给超时兜底
    }
  }

  request(method, params) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this._write({ jsonrpc: '2.0', id, method, params });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`timeout: ${method}`));
        }
      }, 15000);
    });
  }

  notify(method, params) {
    this._write({ jsonrpc: '2.0', method, params });
  }

  onNotification(fn) { this.notificationHandler = fn; }

  initialize(rootPath) {
    return this.request('initialize', {
      rootUri: 'file:///' + rootPath.replace(/\\/g, '/').replace(/^\//, ''),
      capabilities: {},
    });
  }

  dispose() {
    try { this.notify('exit'); } catch (e) { /* ignore */ }
    try { this.proc.kill(); } catch (e) { /* ignore */ }
  }
}

module.exports = { LspClient };
