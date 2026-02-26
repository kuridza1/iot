// src/app/ws.service.ts
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

// NEW: command result stream (used by DS1 widget)
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

  // Public streams
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

    // Update device immediately
    this.device$.next(d0);

    if (this.socket && this.baseUrl === url) {
      // Join the room on existing socket
      try {
        this.socket.emit('set_device', { device: this.device$.value });
      } catch {}
      return;
    }

    // Recreate socket if baseUrl changes
    if (this.socket) {
      try {
        this.socket.disconnect();
      } catch {}
      this.socket = undefined;
    }

    this.baseUrl = url;

    this.socket = io(url, {
      transports: ['websocket'],
      upgrade: false,
      path: '/socket.io',
      query: { device: d0 },
    });

    console.log('[WS] socket created', this.socket?.id, 'url=', url);

    this.socket.on('connect', () => {
      console.log('[WS] connect', this.socket?.id);
      this.zone.run(() => this.connectedSub.next(true));
      try {
        this.socket?.emit('set_device', { device: this.device$.value });
      } catch {}
    });

    this.socket.on('disconnect', (r) => {
      console.log('[WS] disconnect', r);
      this.zone.run(() => this.connectedSub.next(false));
    });

    this.socket.on('connect_error', (e) => {
      console.log('[WS] connect_error', e);
      this.zone.run(() => this.connectedSub.next(false));
    });

    this.socket.on('pin_result', (m: PinResult) => {
      this.zone.run(() => this.pinResultSub.next(m));
    });

    this.socket.on('cmd_result', (m: CmdResult) => {
      // optional debug:
      // console.log('[WS] cmd_result raw', m);
      this.zone.run(() => this.cmdResultSub.next(m));
    });

    this.socket.on('snapshot', (s: Snapshot) => {
      this.zone.run(() => this.snapshotSub.next(s));
    });

    this.socket.on('evt', (e: any) => {
      this.zone.run(() => this.evtSub.next(e));
    });
  }

  setDevice(device: string): void {
    const d = String(device).trim();
    this.device$.next(d);
    try {
      this.socket?.emit('set_device', { device: d });
    } catch {}
  }
}