import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthStore } from '../../core/auth/auth.store';
import { isOnTrial, trialDaysRemaining } from './trial.helpers';

@Component({
  selector: 'app-trial-banner',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './trial-banner.component.html',
  styleUrl: './trial-banner.component.scss',
})
export class TrialBannerComponent {
  private store = inject(AuthStore);

  protected readonly visible = computed(() => isOnTrial(this.store.currentUser()));
  protected readonly days = computed(() => trialDaysRemaining(this.store.currentUser()));
}
