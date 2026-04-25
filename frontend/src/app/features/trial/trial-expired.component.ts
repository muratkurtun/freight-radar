import { Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';
import { AuthStore } from '../../core/auth/auth.store';

@Component({
  selector: 'app-trial-expired',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './trial-expired.component.html',
  styleUrl: './trial.component.scss',
})
export class TrialExpiredComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  protected store = inject(AuthStore);

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
