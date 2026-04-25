import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  protected readonly form = this.fb.nonNullable.group({
    tenant_name: ['', [Validators.required, Validators.maxLength(200)]],
    full_name:   ['', [Validators.required, Validators.maxLength(200)]],
    email:       ['', [Validators.required, Validators.email]],
    password:    ['', [Validators.required, Validators.minLength(8)]],
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
    this.auth.register(this.form.getRawValue()).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/trial-welcome']);
      },
      error: (err) => {
        this.loading.set(false);
        const code = err?.error?.error?.code;
        if (code === 'conflict') {
          this.error.set('Bu e-posta ile zaten bir hesap var.');
        } else {
          this.error.set('Kayıt başarısız. Lütfen bilgileri kontrol edin.');
        }
      },
    });
  }
}
