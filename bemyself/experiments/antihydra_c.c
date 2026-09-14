/* antihydra_c.c — deep counter run for the Antihydra walk (mxdys block method).
 *
 * Port of bemyself/experiments/antihydra_deep.py (validated Python engine) to C
 * with a fast fixed-limb leaf loop and libgmp for the patch-up corrections.
 * Leaf loop uses an 18-step jump table (w18): T^18(2^18 q + r) = 3^18 q + T18[r].
 *
 * Build (no gmp.h needed — prototypes declared below):
 *   gcc -O2 -o antihydra_c antihydra_c.c -l:libgmp.so.10
 *   (fallback: gcc -O2 -o antihydra_c antihydra_c.c /lib/x86_64-linux-gnu/libgmp.so.10)
 *
 * Usage:
 *   ./antihydra_c --depth 34 [--also STEP]...
 *
 * Output (stdout, same lines as the Python engine):
 *   steps=<n> counter=<c> deviation=<c - n/2>
 *   min_counter=<m>
 *   total_steps=<n>
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
static uint8_t  O18[WJ];            /* odds among the 18 steps */
static int8_t   M18[WJ];            /* min cumulative (+2 even / -1 odd), <= 0 */
static const uint64_t MUL3_18 = 387420489ULL;   /* 3**18 */

static void init_jump_table(void) {
    for (uint32_t r0 = 0; r0 < WJ; r0++) {
        uint32_t v = r0;
        int odds = 0, cum = 0, mn = 0;
        for (int i = 0; i < W; i++) {
            if (v & 1) { odds++; cum--; } else { cum += 2; }
            if (cum < mn) mn = cum;
            v += v >> 1;
        }
        T18[r0] = v;
        O18[r0] = (uint8_t)odds;
        M18[r0] = (int8_t)mn;
    }
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
        } else die("usage: antihydra_c --depth N [--also STEP...] [--grid k0 k1 m0 m1]");
    }
    if (gk0 >= 0) {
        for (int k = gk0; k <= gk1; k++)
            for (int m = gm0; m <= gm1; m++) {
                if (n_extra >= (1 << 20)) die("too many targets");
                extras[n_extra++] = (uint64_t)m << (10 + k);
            }
    }
    if (D < BASE_DEP || D > MAX_DEPTH) die("depth out of range (8..40)");

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
    block(x, D, 1, NULL, corr);
    emit(top);
    printf("min_counter=%lld\n", (long long)minimum);
    printf("total_steps=%llu\n", (unsigned long long)steps_total);
    __gmpz_clear(x); __gmpz_clear(corr);
    fprintf(stderr, "# antihydra_c depth=%d targets=%zu elapsed=%.1fs\n",
            D, n_targets, (double)(clock() - t0) / CLOCKS_PER_SEC);
    return 0;
}
