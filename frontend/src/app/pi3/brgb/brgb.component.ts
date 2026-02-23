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
  selector: 'app-brgb',
  standalone: true,
  imports: [CommonModule, HttpClientModule],
  templateUrl: './brgb.component.html',
  styleUrl: './brgb.component.css',
})
export class BrgbComponent implements OnInit, OnDestroy {
  @Input() apiBase = 'http://localhost:5000';
  @Input() device = 'PI3';

  connected = false;
  busy = false;

  // “live” state from telemetry
  liveOn: boolean | null = null;
  liveR = false;
  liveG = false;
  liveB = false;

  // staged state (what user clicks)
  r = false;
  g = false;
  b = false;

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

    if (code !== 'BRGB' && code !== 'BRGB_SET') return;

    const v = evt.value;
    if (!v || typeof v !== 'object') return;

    // Support bool and 0/1
    const r = typeof v.r === 'boolean' ? v.r : !!v.r;
    const g = typeof v.g === 'boolean' ? v.g : !!v.g;
    const b = typeof v.b === 'boolean' ? v.b : !!v.b;

    this.liveR = r;
    this.liveG = g;
    this.liveB = b;

    if (typeof v.on === 'boolean') this.liveOn = v.on;

    // First time we get telemetry, sync staged values to live
    if (this.lastOk === null && !this.busy) {
      this.r = r;
      this.g = g;
      this.b = b;
    }
  }

  private applyCmdResult(msg: CmdResult): void {
    if (!msg || !this.isMine(msg.device)) return;
    const cmd = String(msg.cmd || '');
    if (cmd !== 'PI3_BRGB_SET') return;

    this.busy = false;
    this.lastOk = !!msg.ok;
    this.lastError = msg.error || '';

    window.setTimeout(() => {
      this.lastOk = null;
      this.lastError = '';
    }, 1500);
  }

  toggle(channel: 'r' | 'g' | 'b'): void {
    if (this.busy) return;
    if (channel === 'r') this.r = !this.r;
    if (channel === 'g') this.g = !this.g;
    if (channel === 'b') this.b = !this.b;
  }

  apply(): void {
    if (this.busy) return;

    this.busy = true;
    this.lastOk = null;
    this.lastError = '';

    const url = `${this.apiBase.replace(/\/$/, '')}/cmd`;
    const value = { r: this.r ? 1 : 0, g: this.g ? 1 : 0, b: this.b ? 1 : 0 };

    this.http.post(url, { device: this.device, cmd: 'PI3_BRGB_SET', value }).subscribe({
      next: () => {
        // server will emit cmd_result; telemetry will update live state
      },
      error: (err) => {
        this.busy = false;
        this.lastOk = false;
        this.lastError = err?.error?.error || 'Command failed';
      },
    });
  }

  get dirty(): boolean {
    return this.r !== this.liveR || this.g !== this.liveG || this.b !== this.liveB;
  }
}