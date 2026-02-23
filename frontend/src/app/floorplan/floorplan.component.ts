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

  // [(selectedPi)]
  @Input() selectedPi: PiId = 'PI1';
  @Output() selectedPiChange = new EventEmitter<PiId>();

  @Output() selectedPiChange = new EventEmitter<PiId | null>();
  @Output() selectedElementChange = new EventEmitter<string | null>();
  apiBase = 'http://localhost:5000';
  get selectedElements() {
    if (!this.selectedPi) return [];
    return ELEMENTS.filter(e => e.pi === this.selectedPi);
  }

  selectPi(ev: MouseEvent, id: PiId) {
    ev.stopPropagation();
    this.selectedPiChange.emit(id);
  }
}