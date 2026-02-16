import { Component, EventEmitter, Input, Output } from '@angular/core';
import { ELEMENTS, PANES, PiId } from '../model/smart-house.model';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-floorplan',
  templateUrl: './floorplan.component.html',
  styleUrls: ['./floorplan.component.css'],
  imports: [CommonModule]
})
export class FloorplanComponent {
  panes = PANES;

  @Input() selectedPi: PiId | null = null;
  @Input() selectedElement: string | null = null;

  @Output() selectedPiChange = new EventEmitter<PiId | null>();
  @Output() selectedElementChange = new EventEmitter<string | null>();

  get selectedElements() {
    if (!this.selectedPi) return [];
    return ELEMENTS.filter(e => e.pi === this.selectedPi);
  }

  selectPi(ev: MouseEvent, id: PiId) {
    ev.stopPropagation();
    this.selectedPiChange.emit(id);
    this.selectedElementChange.emit(null);
  }

  selectElement(ev: MouseEvent, elementId: string) {
    ev.stopPropagation();
    this.selectedElementChange.emit(elementId);
  }
}
