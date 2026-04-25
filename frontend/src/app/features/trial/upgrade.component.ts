import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthStore } from '../../core/auth/auth.store';

@Component({
  selector: 'app-upgrade',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './upgrade.component.html',
  styleUrl: './trial.component.scss',
})
export class UpgradeComponent {
  protected store = inject(AuthStore);
}
