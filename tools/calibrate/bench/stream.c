/* Minimal STREAM-style triad (a[i] = b[i] + s*c[i]) for the TME on/off comparison (doc 10 §3 `tme`).
 * Written for VOSS; reports the best of NTIMES runs as "Triad: <MB/s>" like STREAM's report line. */
#include <stdio.h>
#include <stdlib.h>
#include <omp.h>

#ifndef STREAM_ARRAY_SIZE
#define STREAM_ARRAY_SIZE 80000000
#endif
#define NTIMES 10

int main(void) {
    const size_t n = STREAM_ARRAY_SIZE;
    double *a = malloc(n * sizeof(double)), *b = malloc(n * sizeof(double)), *c = malloc(n * sizeof(double));
    if (!a || !b || !c) { fprintf(stderr, "allocation failed\n"); return 1; }
#pragma omp parallel for
    for (size_t i = 0; i < n; i++) { a[i] = 1.0; b[i] = 2.0; c[i] = 0.5; }
    double best = 1e30, s = 3.0;
    for (int k = 0; k < NTIMES; k++) {
        double t = omp_get_wtime();
#pragma omp parallel for
        for (size_t i = 0; i < n; i++) a[i] = b[i] + s * c[i];
        t = omp_get_wtime() - t;
        if (k > 0 && t < best) best = t;
    }
    double check = a[n / 2];
    printf("Triad: %12.1f MB/s (best of %d, check %.1f)\n", 3.0 * sizeof(double) * n / best / 1e6, NTIMES - 1, check);
    free(a); free(b); free(c);
    return 0;
}
