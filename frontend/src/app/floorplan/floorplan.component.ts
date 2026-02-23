import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Dl } from '../pi1/dl/dl';
import { PANES, PiId } from '../model/smart-house.model';

@Component({
  selector: 'app-floorplan',
  standalone: true,
  templateUrl: './floorplan.component.html',
  styleUrls: ['./floorplan.component.css'],
  imports: [CommonModule, Dl]
})
export class FloorplanComponent {
  panes = PANES;
  apiBase = 'http://localhost:5000';
  // [(selectedPi)]
  @Input() selectedPi: PiId = 'PI1';
  @Output() selectedPiChange = new EventEmitter<PiId>();

  // HTML calls selectPi($event, pane.id)
  selectPi(ev: Event, id: PiId): void {
    ev?.preventDefault?.();
    ev?.stopPropagation?.();
    this.selectedPi = id;
    this.selectedPiChange.emit(id);
  }
}