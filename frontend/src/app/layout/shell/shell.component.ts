import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';
import { AuthStore } from '../../core/auth/auth.store';
import { TrialBannerComponent } from '../../shared/trial/trial-banner.component';

interface NavItem {
  path: string;
  label: string;
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, TrialBannerComponent],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  protected store = inject(AuthStore);

  readonly navItems = computed<NavItem[]>(() => {
    const items: NavItem[] = [{ path: '/opportunities', label: 'Opportunities' }];
    if (this.store.isAdmin()) {
      items.push(
        { path: '/reviews/pending', label: 'Pending Reviews' },
        { path: '/pipeline/runs', label: 'Pipeline Runs' },
      );
    }
    return items;
  });

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
