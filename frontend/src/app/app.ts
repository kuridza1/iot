// app.ts
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PANES, PiId } from './model/smart-house.model';
import { FloorplanComponent } from './floorplan/floorplan.component';
import { GrafanaEmbedComponent } from './grafana-embed/grafana-embed.component';
import { Ds1 } from './pi1/ds1/ds1';
import { Dms } from './pi1/dms/dms';
import { SecurityStatus } from './pi1/security-status/security-status';
import { WebCam } from './pi1/web-cam/web-cam';
import { LcdComponent } from './pi3/lcd/lcd.component';
import { BrgbComponent } from './pi3/brgb/brgb.component';
import { WsService } from './ws.service'; // adjust path if needed

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  imports: [
    CommonModule,
    FloorplanComponent,
    GrafanaEmbedComponent,
    Ds1, Dms, WebCam, SecurityStatus,
    LcdComponent, BrgbComponent
  ],
})
export class App implements OnInit {
  apiBase = 'http://localhost:5000';

  private _selectedPi: PiId = 'PI1';
  get selectedPi(): PiId {
    return this._selectedPi;
  }
  set selectedPi(v: PiId) {
    this._selectedPi = v;
    this.ws.setDevice(v);
  }

  constructor(private ws: WsService) {}

  ngOnInit(): void {
    this.ws.ensureConnected(this.apiBase, this.selectedPi);
    this.ws.setDevice(this.selectedPi);
  }

  get grafanaUrl(): string | null {
    const pane = PANES.find(p => p.id === this.selectedPi);
    if (!pane) return null;

    const url = new URL(pane.grafana.dashboardUrl);
    Object.entries(pane.grafana.params ?? {}).forEach(([k, v]) => url.searchParams.set(k, v));
    return url.toString();
  }
}