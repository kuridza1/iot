import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { io, Socket } from 'socket.io-client';

type EvtMsg = {
  device?: string;
  code?: string;
  value?: any;
};

type CmdResult = {
  device?: string;
  cmd?: string;
  ok?: boolean;
  error?: string;
};

@Component({
  selector: 'app-lcd',
  standalone: true,
  imports: [CommonModule, HttpClientModule],
  templateUrl: './lcd.component.html',
  styleUrl: './lcd.component.css',
})
export class LcdComponent implements OnInit, OnDestroy {
  @Input() apiBase = 'http://localhost:5000';
  @Input() device = 'PI3';

  connected = false;
  busy = false;

  enabled: boolean | null = null;

  // LCD preview text published by PI3 as telemetry: code=LCD_TEXT
  text = 'No data';

  lastOk: boolean | null = null;
  lastError = '';

  private sock?: Socket;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.sock = io(this.apiBase, {
      transports: ['websocket'],
      query: { device: this.device },
      reconnection: true,
      reconnectionDelay: 400,
      reconnectionDelayMax: 2500,
    });

    this.sock.on('connect', () => (this.connected = true));
    this.sock.on('disconnect', () => (this.connected = false));

    this.sock.on('evt', (evt: EvtMsg) => this.applyEvt(evt));
    this.sock.on('cmd_result', (msg: CmdResult) => this.applyCmdResult(msg));
  }

  ngOnDestroy(): void {
    try {
      this.sock?.disconnect();
    } catch {}
  }

  private isMine(evtDevice: any): boolean {
    return String(evtDevice || '').toUpperCase() === this.device.toUpperCase();
  }

  private applyEvt(evt: EvtMsg): void {
    if (!evt || !this.isMine(evt.device)) return;
    const code = String(evt.code || '');

    if (code === 'LCD_ENABLED') {
      if (typeof evt.value === 'boolean') this.enabled = evt.value;
      if (typeof evt.value === 'number') this.enabled = !!evt.value;
      return;
    }

    if (code === 'LCD_TEXT') {
      // value is the full rendered string
      this.text = String(evt.value ?? '').trim() || 'No data';
      return;
    }
  }

  private applyCmdResult(msg: CmdResult): void {
    if (!msg || !this.isMine(msg.device)) return;
    const cmd = String(msg.cmd || '');
    if (cmd !== 'PI3_LCD_TOGGLE' && cmd !== 'PI3_LCD_REFRESH') return;

    this.busy = false;
    this.lastOk = !!msg.ok;
    this.lastError = msg.error || '';

    window.setTimeout(() => {
      this.lastOk = null;
      this.lastError = '';
    }, 1500);
  }

  toggle(): void {
    if (this.busy) return;
    this.sendCmd('PI3_LCD_TOGGLE', null);
  }

  refresh(): void {
    if (this.busy) return;
    this.sendCmd('PI3_LCD_REFRESH', null);
  }

  private sendCmd(cmd: string, value: any): void {
    this.busy = true;
    this.lastOk = null;
    this.lastError = '';

    const url = `${this.apiBase.replace(/\/$/, '')}/cmd`;
    this.http.post(url, { device: this.device, cmd, value }).subscribe({
      next: () => {},
      error: (err) => {
        this.busy = false;
        this.lastOk = false;
        this.lastError = err?.error?.error || 'Command failed';
      },
    });
  }

  get stateLabel(): string {
    if (this.enabled === null) return 'UNKNOWN';
    return this.enabled ? 'ON' : 'OFF';
  }
}