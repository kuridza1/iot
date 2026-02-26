import {
  Component, Input, OnDestroy, OnInit, OnChanges, SimpleChanges,
  Inject, PLATFORM_ID, ChangeDetectorRef
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService } from '../../ws.service';

@Component({
  selector: 'app-lcd',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './lcd.component.html',
  styleUrls: ['./lcd.component.css', '../../../widget-frame.css'],
})
export class LcdComponent implements OnInit, OnChanges, OnDestroy {
  @Input() apiBase = 'http://localhost:5000';
  @Input() device = 'PI3';

  connected = false;
  busy = false;

  enabled: boolean | null = null;
  text = 'No data';

  lastOk: boolean | null = null;
  lastError = '';

  private sub = new Subscription();

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;

    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    this.sub.add(this.ws.connected.subscribe(v => {
      this.connected = v;
      this.cdr.detectChanges();
    }));

    this.sub.add(this.ws.evt.subscribe(evt => {
      const code = String(evt?.code || '');

      if (code === 'LCD_ENABLED') {
        const v = evt.value;
        this.enabled = typeof v === 'boolean' ? v : (typeof v === 'number' ? !!v : this.enabled);
        this.cdr.detectChanges();
        return;
      }

      if (code === 'LCD_TEXT') {
        this.text = String(evt.value ?? '').trim() || 'No data';
        this.cdr.detectChanges();
        return;
      }
    }));

    this.sub.add(this.ws.cmdResult.subscribe(msg => {
      const cmd = String(msg?.cmd || '');
      if (cmd !== 'PI3_LCD_TOGGLE' && cmd !== 'PI3_LCD_REFRESH') return;

      this.busy = false;
      this.lastOk = !!msg.ok;
      this.lastError = msg.error || '';
      this.cdr.detectChanges();

      window.setTimeout(() => {
        this.lastOk = null;
        this.lastError = '';
        this.cdr.detectChanges();
      }, 1500);
    }));
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!isPlatformBrowser(this.platformId)) return;

    if (ch['apiBase'] && !ch['apiBase'].firstChange) {
      this.ws.ensureConnected(this.apiBase, this.device);
      this.ws.setDevice(this.device);
    }
    if (ch['device'] && !ch['device'].firstChange) {
      this.ws.setDevice(this.device);
    }
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
  }

  async toggle(ev?: MouseEvent): Promise<void> {
    ev?.stopPropagation();
    if (this.busy) return;

    this.busy = true;
    this.lastOk = null;
    this.lastError = '';
    this.cdr.detectChanges();

    try {
      await this.ws.sendCmdHttp(this.device, 'PI3_LCD_TOGGLE', null);
      window.setTimeout(() => {
        if (this.busy) { this.busy = false; this.cdr.detectChanges(); }
      }, 2000);
    } catch (e: any) {
      this.busy = false;
      this.lastOk = false;
      this.lastError = String(e?.message || e || 'failed');
      this.cdr.detectChanges();
    }
  }
}