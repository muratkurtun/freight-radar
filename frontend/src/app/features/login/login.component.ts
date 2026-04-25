import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';
import { CurrentUser } from '../../core/models/auth.model';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  protected readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.auth.login(this.form.getRawValue()).subscribe({
      next: () => {
        this.auth.fetchCurrentUser().subscribe({
          next: (user) => {
            this.loading.set(false);
            this.router.navigate([this.landingRouteFor(user)]);
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Oturum doğrulanamadı. Tekrar deneyin.');
          },
        });
      },
      error: () => {
        this.loading.set(false);
        this.error.set('E-posta veya şifre hatalı.');
      },
    });
  }

  private landingRouteFor(user: CurrentUser): string {
    if (user.subscription_status === 'expired') return '/trial-expired';
    return '/opportunities';
  }
}
