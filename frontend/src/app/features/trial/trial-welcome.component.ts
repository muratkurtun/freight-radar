import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthStore } from '../../core/auth/auth.store';
import { trialDaysRemaining } from '../../shared/trial/trial.helpers';

@Component({
  selector: 'app-trial-welcome',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './trial-welcome.component.html',
  styleUrl: './trial.component.scss',
})
export class TrialWelcomeComponent {
  private store = inject(AuthStore);

  protected readonly user = this.store.currentUser;
  protected readonly days = computed(() => trialDaysRemaining(this.user()));
}
