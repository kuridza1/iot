import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PANES, PiId } from './model/smart-house.model';
import { FloorplanComponent } from './floorplan/floorplan.component';
import { GrafanaEmbedComponent } from './grafana-embed/grafana-embed.component';
import { Timer } from './timer/timer';
@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  imports: [CommonModule, FloorplanComponent, GrafanaEmbedComponent, Timer],
})
export class App {
  selectedPi: PiId | null = null;
  selectedElement: string | null = null;

  get grafanaUrl(): string | null {
    if (!this.selectedPi) return null;
    const pane = PANES.find(p => p.id === this.selectedPi);
    if (!pane) return null;

    const url = new URL(pane.grafana.dashboardUrl);
    Object.entries(pane.grafana.params ?? {}).forEach(([k, v]) => url.searchParams.set(k, v));
    return url.toString();
  }
}
