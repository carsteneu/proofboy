/* antihydra_c.c — deep counter run for the Antihydra walk (mxdys block method).
 *
 * Port of bemyself/experiments/antihydra_deep.py (validated Python engine) to C
 * with a fixed-limb leaf loop (w18 jump table) and libgmp for the patch-up
 * corrections.  Optional top-correction cache for incremental deepening:
 *   ./antihydra_c --depth 34 --cache-out c34.bin      (save top correction)
 *   ./antihydra_c --depth 35 --cache-in c34.bin       (reuse the left half)
 *
 * Build (no gmp.h needed — prototypes declared below):
 *   gcc -O2 -o antihydra_c antihydra_c.c -l:libgmp.so.10
 *   (fallback: gcc -O2 -o antihydra_c antihydra_c.c /lib/x86_64-linux-gnu/libgmp.so.10)
 *
 * Usage:
 *   ./antihydra_c --depth 34 [--also STEP]... [--grid k0 k1 m0 m1]
 *                [--h-stats KMIN KMAX]    (needs D >= KMAX+14)
 *                [--emit-states KMIN KMAX]   (needs D >= KMAX+13)
 *                [--cache-out FILE] [--cache-in FILE]
 *
 * Output (stdout, same lines as the Python engine):
 *   steps=<n> counter=<c> deviation=<c - n/2>
 *   min_counter=<m>
 *   total_steps=<n>
 *
 * With --cache-in only the lines for steps > 2^(D-1) are emitted (the left
 * half is the cached prefix); min_counter/total_steps are global.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

/* ---- minimal libgmp declarations (host has libgmp.so.10, no headers) ---- */
typedef struct { int _mp_alloc; int _mp_size; unsigned long *_mp_d; } mpz_struct;
typedef mpz_struct mpz_t[1];
typedef mpz_struct *mpz_ptr;
extern void __gmpz_init(mpz_ptr);
extern void __gmpz_clear(mpz_ptr);
extern void __gmpz_set(mpz_ptr, mpz_ptr);
extern void __gmpz_set_ui(mpz_ptr, unsigned long);
extern void __gmpz_mul(mpz_ptr, mpz_ptr, mpz_ptr);
extern void __gmpz_add(mpz_ptr, mpz_ptr, mpz_ptr);
extern void __gmpz_add_ui(mpz_ptr, mpz_ptr, unsigned long);
extern void __gmpz_sub(mpz_ptr, mpz_ptr, mpz_ptr);
extern void __gmpz_fdiv_q_2exp(mpz_ptr, mpz_ptr, unsigned long);
extern void __gmpz_fdiv_r_2exp(mpz_ptr, mpz_ptr, unsigned long);
extern void __gmpz_mul_2exp(mpz_ptr, mpz_ptr, unsigned long);
extern unsigned long __gmpz_sizeinbase(mpz_ptr, int);
extern char *__gmpz_get_str(char *, int, mpz_ptr);
extern int __gmpz_tstbit(mpz_ptr, unsigned long);
extern unsigned long __gmpz_get_ui(mpz_ptr);
extern size_t __gmpz_out_raw(void *stream, mpz_ptr op);
extern size_t __gmpz_inp_raw(mpz_ptr x, void *stream);

#define BASE_DEP 8          /* steps per leaf block: 2**8 = 256 */
#define LIMBS 12            /* leaf buffer: 12*64 = 768 bits (leaf end < 2^406) */
#define NH 8                /* active-limb cap: 8*64 = 512 bits covers the leaf range */
#define MAX_DEPTH 40

static int D;                       /* top depth */
static mpz_t *pow3;                 /* pow3[k] = 3**(2**k), k = BASE_DEP..D-1 */

static uint64_t steps_total = 0;
static int64_t odds_total = 0, evens_total = 0;
static int64_t minimum = 0;
static int64_t cur_counter = 0;

static uint64_t *targets;           /* sorted unique extra targets in steps */
static size_t n_targets = 0, i_target = 0;
static uint64_t next_pow2 = 1;      /* next power-of-two checkpoint */

static uint64_t last_emitted = 0;

static const char *cache_out_path = NULL;
static const char *cache_in_path = NULL;
static int emit_kmin = -1, emit_kmax = -1;
static int hs_kmin = -1, hs_kmax = -1;
static uint8_t *rec_buf = NULL;
static uint64_t rec_lo = 0, rec_hi = 0;

static inline void rec_bit(uint64_t s, int parity) {
    uint64_t b = s - rec_lo;
    if (parity) rec_buf[b >> 3] |= (uint8_t)(1u << (b & 7));
}

static void emit(uint64_t n) {
    if (n == last_emitted) return;      /* power-of-two / extra-target collision */
    last_emitted = n;
    int64_t counter = 2 * evens_total - odds_total;
    int64_t deviation = counter - (int64_t)(n / 2);
    printf("steps=%llu counter=%lld deviation=%lld\n",
           (unsigned long long)n, (long long)counter, (long long)deviation);
}

static void die(const char *msg) { fprintf(stderr, "%s\n", msg); exit(2); }

/* ---- w18 jump table: T^18(2^18 q + r) = 3^18 q + T18[r] ------------------
 * For i < 18, x_i = T^i(2^18 q + r) = 3^i * 2^(18-i) * q + T^i(r): the q term
 * is even, so the parity word of the 18 steps (and hence counter/minimum
 * deltas) depends only on r = x mod 2^18. */
#define W 18
#define WJ (1u << W)
static uint32_t T18[WJ];
static uint32_t P18[WJ];            /* bit i = parity (1=odd) of the value at step i */
static uint8_t  O18[WJ];            /* odds among the 18 steps */
static int8_t   M18[WJ];            /* min cumulative (+2 even / -1 odd), <= 0 */
static const uint64_t MUL3_18 = 387420489ULL;   /* 3**18 */

static void init_jump_table(void) {
    for (uint32_t r0 = 0; r0 < WJ; r0++) {
        uint32_t v = r0, pm = 0;
        int odds = 0, cum = 0, mn = 0;
        for (int i = 0; i < W; i++) {
            if (v & 1) { odds++; cum--; pm |= (1u << i); } else { cum += 2; }
            if (cum < mn) mn = cum;
            v += v >> 1;
        }
        T18[r0] = v;
        O18[r0] = (uint8_t)odds;
        M18[r0] = (int8_t)mn;
        P18[r0] = pm;
    }
}

/* ---- top-correction cache (left half of a depth-(d+1) block) ---- */
#define CACHE_MAGIC "AHYC1\0\0\0"

static void write_cache(const char *path, mpz_ptr c, uint64_t depth,
                        int64_t odds, int64_t evens, int64_t mn) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot open cache-out file");
    if (fwrite(CACHE_MAGIC, 1, 8, f) != 8) die("cache write failed");
    if (fwrite(&depth, 8, 1, f) != 1) die("cache write failed");
    if (fwrite(&odds, 8, 1, f) != 1) die("cache write failed");
    if (fwrite(&evens, 8, 1, f) != 1) die("cache write failed");
    if (fwrite(&mn, 8, 1, f) != 1) die("cache write failed");
    __gmpz_out_raw(f, c);
    if (fclose(f)) die("cache write failed");
}

static void read_cache(const char *path, mpz_ptr c, uint64_t *depth,
                       int64_t *odds, int64_t *evens, int64_t *mn) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot open cache-in file");
    char magic[8];
    if (fread(magic, 1, 8, f) != 8 || memcmp(magic, CACHE_MAGIC, 8) != 0)
        die("cache-in: bad magic");
    if (fread(depth, 8, 1, f) != 1) die("cache-in: bad header");
    if (fread(odds, 8, 1, f) != 1) die("cache-in: bad header");
    if (fread(evens, 8, 1, f) != 1) die("cache-in: bad header");
    if (fread(mn, 8, 1, f) != 1) die("cache-in: bad header");
    if (__gmpz_inp_raw(c, f) == 0) die("cache-in: bad mpz payload");
    fclose(f);
}

/* ---- leaf: run `end - steps_total` steps (split at checkpoint boundaries) ---- */
static void run_leaf(mpz_ptr x_in, mpz_ptr x_end_out) {
    uint64_t l[LIMBS];
    memset(l, 0, sizeof l);
    int ms = x_in[0]._mp_size;
    if (ms < 0) die("negative value in leaf");
    if (ms > 4) die("leaf input wider than 256 bits");
    for (int i = 0; i < ms; i++) l[i] = x_in[0]._mp_d[i];
    int active = ms < 1 ? 1 : ms + 1;   /* working limbs for the x += x>>1 loop */
    if (active > NH) active = NH;

    uint64_t end = steps_total + (1ULL << BASE_DEP);
    while (steps_total < end) {
        uint64_t split = end;
        if (next_pow2 < split) split = next_pow2;
        if (i_target < n_targets && targets[i_target] < split) split = targets[i_target];
        if (split <= steps_total) split = steps_total + 1;  /* safety */

        for (uint64_t s = steps_total; s < split; ) {
            if (split - s >= W) {
                /* one 18-step jump */
                uint32_t r = (uint32_t)(l[0] & (WJ - 1u));
                if (rec_buf) {
                    uint32_t mk = P18[r];
                    for (int ri = 0; ri < W; ri++) {
                        uint64_t ss = s + (uint64_t)ri;
                        if (ss >= rec_lo && ss < rec_hi) rec_bit(ss, (int)((mk >> ri) & 1u));
                    }
                }
                int odds = O18[r];
                odds_total += odds;
                evens_total += W - odds;
                cur_counter += 36 - 3 * odds;
                if (cur_counter + M18[r] < minimum) minimum = cur_counter + M18[r];
                /* l = (l >> 18) * 3^18 + T18[r] */
                int lim = active + 2;
                if (lim > LIMBS) lim = LIMBS;
                unsigned __int128 carry = T18[r];
                int i = 0;
                for (; i < lim; i++) {
                    unsigned long long hi = (i + 1 < LIMBS) ? l[i + 1] : 0;
                    unsigned long long q = (l[i] >> W) | (hi << (64 - W));
                    unsigned __int128 acc = (unsigned __int128)q * MUL3_18 + carry;
                    l[i] = (unsigned long long)acc;
                    carry = acc >> 64;
                }
                if (carry) {
                    if (i >= LIMBS) die("limb overflow in w18 jump");
                    l[i] = (unsigned long long)carry;
                    i++;
                }
                for (int j = i; j < LIMBS; j++) l[j] = 0;
                active = LIMBS;
                while (active > 1 && l[active - 1] == 0) active--;
                if (active < NH) active++;
                s += W;
            } else {
                if (rec_buf && s >= rec_lo && s < rec_hi) rec_bit(s, (int)(l[0] & 1));
                if (l[0] & 1) {
                    odds_total++;
                    cur_counter--;
                } else {
                    evens_total++;
                    cur_counter += 2;
                }
                if (cur_counter < minimum) minimum = cur_counter;
                /* x = x + (x >> 1); s[i] = (l[i]>>1) | ((l[i+1]&1)<<63) */
                unsigned long long ca = 0;
                for (int i = 0; i < active; i++) {
                    unsigned long long c = l[i];
                    unsigned long long hi = (i + 1 < LIMBS) ? l[i + 1] : 0;
                    unsigned long long shifted = (c >> 1) | ((hi & 1ULL) << 63);
                    unsigned long long sum = c + shifted;
                    unsigned long long c1 = (sum < c);
                    unsigned long long sum2 = sum + ca;
                    unsigned long long c2 = (sum2 < sum);
                    ca = c1 | c2;
                    l[i] = sum2;
                }
                if (ca && active < LIMBS) l[active] = ca;
                if (active < NH && l[active - 1]) active++;
                s++;
            }
        }
        steps_total = split;
        if (steps_total == next_pow2) {
            emit(steps_total);
            next_pow2 <<= 1;
        }
        if (i_target < n_targets && steps_total == targets[i_target]) {
            emit(steps_total);
            i_target++;
        }
    }

    /* limbs -> mpz */
    __gmpz_set_ui(x_end_out, 0);
    for (int i = LIMBS - 1; i >= 0; i--) {
        __gmpz_mul_2exp(x_end_out, x_end_out, 64);
        if (l[i]) __gmpz_add_ui(x_end_out, x_end_out, l[i]);
    }
}

/* ---- block: (value, correction) for 2**dep steps from the true value x ---- */
static void block(mpz_ptr x, int dep, int last, mpz_ptr value_out, mpz_ptr corr_out) {
    mpz_t original, xm, v1, c1, c2, t, xe;
    __gmpz_init(original); __gmpz_init(xm);
    __gmpz_init(v1); __gmpz_init(c1); __gmpz_init(c2); __gmpz_init(t);
    __gmpz_init(xe);
    __gmpz_set(original, x);

    unsigned long long n = 1ULL << dep;  /* steps and shift width */
    if (__gmpz_sizeinbase(x, 2) > n) __gmpz_fdiv_r_2exp(xm, x, n);
    else __gmpz_set(xm, x);

    if (dep <= BASE_DEP) {
        run_leaf(xm, xe);
        /* correction = pow3[dep]*start - (x_end << n) */
        __gmpz_mul(corr_out, pow3[dep], xm);
        __gmpz_mul_2exp(t, xe, n);
        __gmpz_sub(corr_out, corr_out, t);
    } else {
        block(xm, dep - 1, 0, v1, c1);
        block(v1, dep - 1, 1, NULL, c2);
        unsigned long long half = 1ULL << (dep - 1);
        __gmpz_mul(corr_out, c1, pow3[dep - 1]);
        __gmpz_mul_2exp(t, c2, half);
        __gmpz_add(corr_out, corr_out, t);
    }
    if (!last) {
        __gmpz_mul(value_out, original, pow3[dep]);
        __gmpz_sub(value_out, value_out, corr_out);
        __gmpz_fdiv_q_2exp(value_out, value_out, n);
    }
    __gmpz_clear(original); __gmpz_clear(xm);
    __gmpz_clear(v1); __gmpz_clear(c1); __gmpz_clear(c2); __gmpz_clear(t);
    __gmpz_clear(xe);
}

/* ---- boundary-state diagnostics (--emit-states): exact x_n reports ------ */
static void emit_state(long long k, int j, uint64_t n, mpz_ptr x) {
    unsigned long bits = __gmpz_sizeinbase(x, 2);
    mpz_t t, v, u;
    __gmpz_init(t); __gmpz_init(v); __gmpz_init(u);
    char *b64 = malloc(2100), *b256 = malloc(2100), *b1024 = malloc(2100);
    char *b4096 = malloc(2100), *btop = malloc(2100);
    __gmpz_fdiv_r_2exp(t, x, 64);    __gmpz_get_str(b64, 16, t);
    __gmpz_fdiv_r_2exp(t, x, 256);   __gmpz_get_str(b256, 16, t);
    __gmpz_fdiv_r_2exp(t, x, 1024);  __gmpz_get_str(b1024, 16, t);
    __gmpz_fdiv_r_2exp(t, x, 4096);  __gmpz_get_str(b4096, 16, t);
    if (bits > 256) __gmpz_fdiv_q_2exp(t, x, bits - 256); else __gmpz_set(t, x);
    __gmpz_get_str(btop, 16, t);
    /* carry word of 3*x on 32-bit limbs, low 128 limbs (R35 3.4C) */
    static char carry[160];
    uint64_t a[128];
    __gmpz_fdiv_r_2exp(v, x, 4096);
    for (int h = 0; h < 128; h++) {
        __gmpz_fdiv_r_2exp(u, v, 32);
        a[h] = (uint64_t)__gmpz_get_ui(u);
        __gmpz_fdiv_q_2exp(v, v, 32);
    }
    uint64_t c = 0; int nnz = 0, run = 0, maxrun = 0;
    for (int h = 0; h < 128; h++) {
        uint64_t uu = 3 * a[h] + c;
        c = uu >> 32;
        carry[h] = (char)('0' + (int)c);
        if (c) { nnz++; run++; if (run > maxrun) maxrun = run; } else run = 0;
    }
    carry[128] = 0;
    /* next 512 step parities, derived from x mod 2^1024 */
    static char par[520];
    __gmpz_fdiv_r_2exp(v, x, 1024);
    for (int i = 0; i < 512; i++) {
        par[i] = (char)('0' + (__gmpz_tstbit(v, 0) ? 1 : 0));
        __gmpz_fdiv_q_2exp(u, v, 1);
        __gmpz_add(v, v, u);
        __gmpz_fdiv_r_2exp(v, v, 1024);
    }
    par[512] = 0;
    printf("state k=%lld j=%d n=%llu bits=%lu low64=0x%s low256=0x%s low1024=0x%s low4096=0x%s top256=0x%s carries=%s carry_nnz=%d carry_maxrun=%d parity=%s\n",
           k, j, (unsigned long long)n, bits, b64, b256, b1024, b4096, btop,
           carry, nnz, maxrun, par);
    free(b64); free(b256); free(b1024); free(b4096); free(btop);
    __gmpz_clear(t); __gmpz_clear(v); __gmpz_clear(u);
}

static int cmp_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv) {
    D = 0;
    static uint64_t extras[1 << 20];
    size_t n_extra = 0;
    int gk0 = -1, gk1 = -1, gm0 = 0, gm1 = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--depth") && i + 1 < argc) D = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--also") && i + 1 < argc) {
            if (n_extra >= (1 << 20)) die("too many targets");
            extras[n_extra++] = strtoull(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--grid") && i + 4 < argc) {
            gk0 = atoi(argv[++i]); gk1 = atoi(argv[++i]);
            gm0 = atoi(argv[++i]); gm1 = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--cache-out") && i + 1 < argc) {
            cache_out_path = argv[++i];
        } else if (!strcmp(argv[i], "--cache-in") && i + 1 < argc) {
            cache_in_path = argv[++i];
        } else if (!strcmp(argv[i], "--emit-states") && i + 2 < argc) {
            emit_kmin = atoi(argv[++i]);
            emit_kmax = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--h-stats") && i + 2 < argc) {
            hs_kmin = atoi(argv[++i]);
            hs_kmax = atoi(argv[++i]);
        } else die("usage: antihydra_c --depth N [--also STEP...] [--grid k0 k1 m0 m1] [--cache-out FILE] [--cache-in FILE] [--emit-states KMIN KMAX] [--h-stats KMIN KMAX]");
    }
    if (gk0 >= 0) {
        for (int k = gk0; k <= gk1; k++)
            for (int m = gm0; m <= gm1; m++) {
                if (n_extra >= (1 << 20)) die("too many targets");
                extras[n_extra++] = (uint64_t)m << (10 + k);
            }
    }
    if (D < BASE_DEP || D > MAX_DEPTH) die("depth out of range (8..40)");
    if (cache_in_path && D <= BASE_DEP) die("cache-in needs depth > BASE_DEP");
    if (emit_kmax >= 0) {
        if (emit_kmin < 0 || emit_kmax < emit_kmin || (long long)D < (long long)emit_kmax + 13)
            die("emit-states needs 0 <= kmin <= kmax and depth D >= kmax+13");
        if (cache_in_path || cache_out_path) die("emit-states cannot be combined with cache options");
    }
    if (hs_kmax >= 0) {
        if (hs_kmin < 0 || hs_kmax < hs_kmin || (long long)D < (long long)hs_kmax + 14)
            die("h-stats needs 0 <= kmin <= kmax and depth D >= kmax+14");
        if (cache_in_path || cache_out_path || emit_kmax >= 0)
            die("h-stats cannot be combined with cache/emit-states options");
    }

    uint64_t top = 1ULL << D;
    /* filter + sort + dedup extra targets */
    targets = malloc(sizeof(uint64_t) * (n_extra + 1));
    size_t m = 0;
    for (size_t i = 0; i < n_extra; i++)
        if (extras[i] > 0 && extras[i] <= top) targets[m++] = extras[i];
    qsort(targets, m, sizeof(uint64_t), cmp_u64);
    size_t u = 0;
    for (size_t i = 0; i < m; i++)
        if (u == 0 || targets[i] != targets[u - 1]) targets[u++] = targets[i];
    n_targets = u;

    init_jump_table();

    /* pow3[k] = 3**(2**k) for k = BASE_DEP..D-1 by repeated squaring */
    pow3 = malloc(sizeof(mpz_t) * (D + 1));
    mpz_t value;
    __gmpz_init(value); __gmpz_set_ui(value, 3);
    for (int k = 0; k <= D; k++) {
        if (k >= BASE_DEP && k <= D - 1) {
            __gmpz_init(pow3[k]);
            __gmpz_set(pow3[k], value);
        }
        if (k < D) {
            mpz_t sq;
            __gmpz_init(sq);
            __gmpz_mul(sq, value, value);
            __gmpz_set(value, sq);
            __gmpz_clear(sq);
        }
    }
    __gmpz_clear(value);

    clock_t t0 = clock();
    mpz_t x, corr;
    __gmpz_init(x); __gmpz_init(corr);
    __gmpz_set_ui(x, 8);

    if (hs_kmax >= 0) {
        /* pattern-statistics walk: 3-bit pattern (f(t),f(2t),f(2t+1)) per epoch block */
        uint64_t T = 1ULL << (hs_kmax + 14);
        rec_lo = 1ULL << (hs_kmin + 12);
        rec_hi = T;
        rec_buf = calloc((size_t)((T - rec_lo) / 8 + 2), 1);
        if (!rec_buf) die("h-stats buffer allocation failed");
        mpz_t v, ch;
        __gmpz_init(v); __gmpz_init(ch);
        block(x, hs_kmin + 12, 0, v, ch);
        __gmpz_set(x, v);
        for (int m = hs_kmin + 12; m <= hs_kmax + 13; m++) {
            block(x, m, 0, v, ch);
            __gmpz_set(x, v);
        }
        if (steps_total != T) die("h-stats walk/bookkeeping mismatch");
        static const int hvs[6] = {120, 54, -12, 10, -56, -122};
        for (int k = hs_kmin; k <= hs_kmax; k++) {
            uint64_t L1 = 4ULL << (k + 10);
            uint64_t base = 4ULL << (k + 10);
            long long cnt[6] = {0,0,0,0,0,0};
            long long pat[8] = {0,0,0,0,0,0,0,0};
            long long S1 = 0, S2 = 0;
            for (uint64_t t = base; t < base + L1; t++) {
                uint64_t i1 = t - rec_lo, i2 = 2*t - rec_lo, i3 = 2*t + 1 - rec_lo;
                int p1 = (rec_buf[i1 >> 3] >> (i1 & 7)) & 1;
                int p2 = (rec_buf[i2 >> 3] >> (i2 & 7)) & 1;
                int p3 = (rec_buf[i3 >> 3] >> (i3 & 7)) & 1;
                pat[p1 | (p2 << 1) | (p3 << 2)]++;
                int f1 = p1 ? -1 : 1, f2 = p2 ? -1 : 1, f3 = p3 ? -1 : 1;
                long long h = 55LL*f1 - 33LL*(f2+f3) - 1;
                int idx;
                if      (h == 120) idx = 0;
                else if (h == 54)  idx = 1;
                else if (h == -12) idx = 2;
                else if (h == 10)  idx = 3;
                else if (h == -56) idx = 4;
                else if (h == -122) idx = 5;
                else { die("h value outside the six-value set"); idx = 0; }
                cnt[idx]++;
                S1 += f1; S2 += f2 + f3;
            }
            long long Dsum = 0;
            for (int z = 0; z < 6; z++) Dsum += cnt[z] * (long long)hvs[z];
            if (Dsum != 55*S1 - 33*S2 - (long long)L1) die("h-stats internal consistency failed");
            printf("hstats k=%d L1=%llu D=%lld mean_h=%.6f S1=%lld S2=%lld hist{120:%lld,54:%lld,-12:%lld,10:%lld,-56:%lld,-122:%lld}\n",
                   k, (unsigned long long)L1, Dsum, (double)Dsum/(double)L1, S1, S2,
                   cnt[0], cnt[1], cnt[2], cnt[3], cnt[4], cnt[5]);
            printf("hstats-pat k=%d p1+2p2+4p3(1=odd): [%lld %lld %lld %lld %lld %lld %lld %lld]\n",
                   k, pat[0], pat[1], pat[2], pat[3], pat[4], pat[5], pat[6], pat[7]);
        }
        printf("min_counter=%lld\n", (long long)minimum);
        printf("total_steps=%llu\n", (unsigned long long)steps_total);
        __gmpz_clear(v); __gmpz_clear(ch);
        __gmpz_clear(x); __gmpz_clear(corr);
        fprintf(stderr, "# antihydra_c h-stats kmin=%d kmax=%d elapsed=%.1fs\n",
                hs_kmin, hs_kmax, (double)(clock() - t0) / CLOCKS_PER_SEC);
        return 0;
    }
    if (emit_kmax >= 0) {
        /* boundary-state walk: exact x_n at n = (4+j)L_k (R35 3.4B) */
        mpz_t v, c;
        __gmpz_init(v); __gmpz_init(c);
        uint64_t n = 0;
        block(x, emit_kmin + 12, 0, v, c);       /* reach 4L_kmin = 2^(kmin+12) */
        __gmpz_set(x, v);
        n = 1ULL << (emit_kmin + 12);
        emit_state(emit_kmin, 0, n, x);
        for (int k = emit_kmin; k <= emit_kmax; k++) {
            for (int j = 1; j <= 4; j++) {
                block(x, k + 10, 0, v, c);       /* next epoch boundary */
                __gmpz_set(x, v);
                n += 1ULL << (k + 10);
                emit_state(k, j, n, x);
            }
            if (k < emit_kmax) emit_state(k + 1, 0, n, x);  /* 8L_k = 4L_(k+1) */
        }
        if (n != steps_total) die("emit-states walk/bookkeeping mismatch");
        printf("min_counter=%lld\n", (long long)minimum);
        printf("total_steps=%llu\n", (unsigned long long)steps_total);
        __gmpz_clear(v); __gmpz_clear(c);
        __gmpz_clear(x); __gmpz_clear(corr);
        fprintf(stderr, "# antihydra_c emit-states kmin=%d kmax=%d elapsed=%.1fs\n",
                emit_kmin, emit_kmax, (double)(clock() - t0) / CLOCKS_PER_SEC);
        return 0;
    }
    if (cache_in_path) {
        /* Left half [0, 2^(D-1)) comes from the cache; the right half is
         * computed fresh from v1 = phi^(2^(D-1))(8) = (8*3^(2^(D-1)) - c1) >> 2^(D-1). */
        uint64_t cdep; int64_t codds, cevens, cmin;
        mpz_t c1, c2, vtmp, v1c, tt;
        __gmpz_init(c1); __gmpz_init(c2); __gmpz_init(vtmp);
        __gmpz_init(v1c); __gmpz_init(tt);
        read_cache(cache_in_path, c1, &cdep, &codds, &cevens, &cmin);
        if (cdep + 1 != (uint64_t)D) die("cache depth mismatch (expected D-1)");
        odds_total = codds; evens_total = cevens; minimum = cmin;
        cur_counter = 2 * evens_total - odds_total;
        steps_total = 1ULL << (D - 1);
        while (i_target < n_targets && targets[i_target] <= steps_total) i_target++;
        next_pow2 = 1ULL << D;      /* only the top boundary remains ahead */
        __gmpz_mul_2exp(vtmp, pow3[D - 1], 3);            /* 8 * 3^(2^(D-1)) */
        __gmpz_sub(vtmp, vtmp, c1);
        __gmpz_fdiv_q_2exp(v1c, vtmp, (unsigned long)(1ULL << (D - 1)));
        block(v1c, D - 1, 1, NULL, c2);
        if (cache_out_path) {
            __gmpz_mul(corr, c1, pow3[D - 1]);
            __gmpz_mul_2exp(tt, c2, (unsigned long)(1ULL << (D - 1)));
            __gmpz_add(corr, corr, tt);
        }
        __gmpz_clear(c1); __gmpz_clear(c2); __gmpz_clear(vtmp);
        __gmpz_clear(v1c); __gmpz_clear(tt);
    } else {
        block(x, D, 1, NULL, corr);
    }
    emit(top);
    printf("min_counter=%lld\n", (long long)minimum);
    printf("total_steps=%llu\n", (unsigned long long)steps_total);
    if (cache_out_path)
        write_cache(cache_out_path, corr, (uint64_t)D,
                    odds_total, evens_total, minimum);
    __gmpz_clear(x); __gmpz_clear(corr);
    fprintf(stderr, "# antihydra_c depth=%d targets=%zu%s%s elapsed=%.1fs\n",
            D, n_targets,
            cache_in_path ? " cache-in" : "",
            cache_out_path ? " cache-out" : "",
            (double)(clock() - t0) / CLOCKS_PER_SEC);
    return 0;
}
