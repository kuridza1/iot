import {
  Component,
  Inject,
  Input,
  OnDestroy,
  OnInit,
  PLATFORM_ID,
  NgZone
} from '@angular/core';

import { CommonModule, isPlatformBrowser } from '@angular/common';

@Component({
  selector: 'app-dl',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dl.html',
  styleUrls: ['./dl.css'],
})
export class Dl implements OnInit, OnDestroy {

  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';

  @Input() top = '50%';
  @Input() left = '50%';
  @Input() sizePx = 20;

  dlOn: boolean | null = null;

  private es?: EventSource;
  private isBrowser = false;

  constructor(
    @Inject(PLATFORM_ID) platformId: object,
    private zone: NgZone
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    if (!this.isBrowser) return;
    this.connect();
  }

  ngOnDestroy(): void {
    this.es?.close();
  }

  private connect(): void {
    const url = `${this.apiBase}/events?device=${this.device}`;

    this.es = new EventSource(url);

    this.es.addEventListener('snapshot', (msg: MessageEvent) => {
      const snap = JSON.parse(msg.data);
      const dl = snap?.actuators?.DL;

      this.zone.run(() => {
        if (dl !== undefined) this.dlOn = !!dl;
      });
    });

    this.es.addEventListener('evt', (msg: MessageEvent) => {
      const ev = JSON.parse(msg.data);

      if (ev.kind === 'actuator' && ev.code === 'DL') {
        this.zone.run(() => {
          this.dlOn = !!ev.value;
        });
      }
    });
  }
}