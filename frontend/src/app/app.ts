// app.ts
import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PANES, PiId } from './model/smart-house.model';
import { FloorplanComponent } from './floorplan/floorplan.component';
import { GrafanaEmbedComponent } from './grafana-embed/grafana-embed.component';
import { Timer } from './pi2/timer/timer';
import { Gsg } from './pi2/gsg/gsg';
import { Ds1 } from './pi1/ds1/ds1';
import { Dms } from './pi1/dms/dms';
import { SecurityStatus } from './pi1/security-status/security-status';
import { WebCam } from './pi1/web-cam/web-cam';
import { LcdComponent } from './pi3/lcd/lcd.component';
import { BrgbComponent } from './pi3/brgb/brgb.component';
import { WsService } from './ws.service';
import { LightSwitch } from './pi1/light-switch/light-switch.component';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [
    CommonModule,
    FloorplanComponent,
    GrafanaEmbedComponent,
    Ds1, Dms, WebCam, SecurityStatus,
    LcdComponent, BrgbComponent, LightSwitch,
    Timer, Gsg
  ],
})
export class App implements OnInit, OnDestroy {
  apiBase = 'http://localhost:5000';
  alarmActive = false;

  private _selectedPi: PiId = 'PI1';
  private subs = new Subscription();

  get selectedPi(): PiId { return this._selectedPi; }
  set selectedPi(v: PiId) {
    this._selectedPi = v;
    this.ws.setDevice(v);
  }

  constructor(private ws: WsService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.ws.ensureConnected(this.apiBase, this.selectedPi);
    this.ws.setDevice(this.selectedPi);

    this.subs.add(
      this.ws.rawSnapshot.subscribe((snap: any) => {
        if (snap?.device !== 'PI1') return;

        // Prefer "system_state" (or whatever your snapshot uses for AlarmState),
        // and only treat ALARM as active.
        const st = String(snap?.system_state ?? '').toUpperCase();
        this.alarmActive = (st === 'ALARM');

        this.cdr.markForCheck();
      })
    );

    this.subs.add(
      this.ws.rawEvt.subscribe((evt: any) => {
        if (evt?.device !== 'PI1') return;

        const code = String(evt?.code || '');
        if (code === 'ALARM_STATE') {
          this.alarmActive = String(evt.value).toUpperCase() === 'ALARM';
          this.cdr.markForCheck();
        }

        // IMPORTANT: remove/ignore ALARM_ACTIVE so it can't trigger flashing
        // in non-ALARM states.
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  get grafanaUrl(): string | null {
    const pane = PANES.find(p => p.id === this.selectedPi);
    if (!pane) return null;
    const url = new URL(pane.grafana.dashboardUrl);
    Object.entries(pane.grafana.params ?? {}).forEach(([k, v]) => url.searchParams.set(k, v));
    return url.toString();
  }
}