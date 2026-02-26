import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';
import { filter, shareReplay } from 'rxjs/operators';
import { io, Socket } from 'socket.io-client';

export type Snapshot = {
  device: string;
  system_state?: string | null;
  alarm_active?: boolean;
  alarm_reason?: string | null;
  people_inside?: number;
  db_on?: boolean | null;
};

export type PinResult = { device?: string; ok: boolean; error?: string; ts?: number };

export type CmdResult = {
  device?: string;
  cmd?: string;
  ok: boolean;
  error?: string;
  value?: any;
  ts?: number;
};

@Injectable({ providedIn: 'root' })
export class WsService {
  private socket?: Socket;
  private baseUrl?: string;

  private device$ = new BehaviorSubject<string>('PI1');

  private pinResultSub = new Subject<PinResult>();
  private cmdResultSub = new Subject<CmdResult>();
  private snapshotSub = new Subject<Snapshot>();
  private evtSub = new Subject<any>();
  private connectedSub = new BehaviorSubject<boolean>(false);

  connected: Observable<boolean> = this.connectedSub.asObservable().pipe(shareReplay(1));

  pinResult: Observable<PinResult> = this.pinResultSub.asObservable().pipe(
    filter((m) => !m.device || String(m.device).trim() === String(this.device$.value).trim()),
    shareReplay(1),
  );

  cmdResult: Observable<CmdResult> = this.cmdResultSub.asObservable().pipe(
    filter((m) => !m.device || String(m.device).trim() === String(this.device$.value).trim()),
    shareReplay(1),
  );

  snapshot: Observable<Snapshot> = this.snapshotSub.asObservable().pipe(
    filter((s) => String(s?.device || '').trim() === String(this.device$.value).trim()),
    shareReplay(1),
  );

  evt: Observable<any> = this.evtSub.asObservable().pipe(
    filter((e) => !e?.device || String(e.device).trim() === String(this.device$.value).trim()),
    shareReplay(1),
  );

  constructor(private zone: NgZone) {}

  ensureConnected(apiBase: string, initialDevice = 'PI1'): void {
    const url = apiBase.replace(/\/+$/, '');
    const d0 = String(initialDevice).trim();

    this.device$.next(d0);

    if (this.socket && this.baseUrl === url) {
      try { this.socket.emit('set_device', { device: this.device$.value }); } catch {}
      return;
    }

    if (this.socket) {
      try { this.socket.disconnect(); } catch {}
      this.socket = undefined;
    }

    this.baseUrl = url;

    this.socket = io(url, {
      transports: ['websocket'],
      upgrade: false,
      path: '/socket.io',
      query: { device: d0 },
    });

    this.socket.on('connect', () => {
      this.zone.run(() => this.connectedSub.next(true));
      try { this.socket?.emit('set_device', { device: this.device$.value }); } catch {}
    });

    this.socket.on('disconnect', () => this.zone.run(() => this.connectedSub.next(false)));
    this.socket.on('connect_error', () => this.zone.run(() => this.connectedSub.next(false)));

    this.socket.on('pin_result', (m: PinResult) => this.zone.run(() => this.pinResultSub.next(m)));
    this.socket.on('cmd_result', (m: CmdResult) => this.zone.run(() => this.cmdResultSub.next(m)));
    this.socket.on('snapshot', (s: Snapshot) => this.zone.run(() => this.snapshotSub.next(s)));
    this.socket.on('evt', (e: any) => this.zone.run(() => this.evtSub.next(e)));
  }

  setDevice(device: string): void {
    const d = String(device).trim();
    this.device$.next(d);
    try { this.socket?.emit('set_device', { device: d }); } catch {}
  }

  // IMPORTANT: commands go over HTTP POST /cmd (server already implements this)
  async sendCmdHttp(device: string, cmd: string, value: any = null): Promise<void> {
    const base = (this.baseUrl || '').replace(/\/+$/, '');
    if (!base) throw new Error('WsService not initialized. Call ensureConnected() first.');

    const payload = { device: String(device).trim(), cmd: String(cmd).trim(), value };

    const res = await fetch(`${base}/cmd`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j?.error) msg = String(j.error);
      } catch {}
      throw new Error(msg);
    }
  }
}