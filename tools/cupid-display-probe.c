/*
 * Cupid scanout diagnostic. No UEFI, storage, USB or MMIO writes.
 * Register offsets: MiCode/Xiaomi_Kernel_OpenSource zeus-s-oss revision
 * 7d10d738b2c4299f3b8549c61a01ece39f19c788, dpu_hw_sspp.c / dpu_hw_catalog.c.
 * MDSS base and eight source-pipe offsets: supplied Cupid runtime FDT.
 * Register addresses may be IOVAs, not CPU physical addresses. Only candidates
 * wholly inside the known splash reservation are eligible; eligibility is not
 * proof that a pipe is active. Raw values remain visible for all eight pipes.
 */
#include <stdint.h>

#define SPLASH_BASE 0xb8000000ULL
#define SPLASH_END  0xbab00000ULL
#define MDSS_BASE   0x0ae00000ULL

struct pipe {
  uint32_t size, xy, out_size, address, stride, format, unpack, op;
};
struct surface {
  uint64_t base;
  uint32_t width, height, stride;
};
static const uint32_t offsets[8] = {
  0x5000, 0x7000, 0x9000, 0xb000, 0x25000, 0x27000, 0x29000, 0x2b000
};
static const uint8_t glyphs[][7] = {
  {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14},
  {14,17,1,2,4,8,31}, {30,1,1,14,1,1,30},
  {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
  {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8},
  {14,17,17,14,17,17,14}, {14,17,17,15,1,1,14},
  {14,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
  {14,17,16,16,16,17,14}, {30,17,17,17,17,17,30},
  {31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
  {14,17,16,23,17,17,15}, {17,17,17,31,17,17,17},
  {14,4,4,4,4,4,14}, {7,2,2,2,18,18,12},
  {17,18,20,24,20,18,17}, {16,16,16,16,16,16,31},
  {17,27,21,21,17,17,17}, {17,25,21,19,17,17,17},
  {14,17,17,17,17,17,14}, {30,17,17,30,16,16,16},
  {14,17,17,17,21,18,13}, {30,17,17,30,20,18,17},
  {15,16,16,14,1,1,30}, {31,4,4,4,4,4,4},
  {17,17,17,17,17,17,14}, {17,17,17,17,17,10,4},
  {17,17,17,21,21,21,10}, {17,17,10,4,10,17,17},
  {17,17,10,4,4,4,4}, {31,1,2,4,8,16,31}
};

extern void probe_reset(void) __attribute__((noreturn));

static __attribute__((noinline)) void delay(uint32_t seconds)
{
  uint64_t freq, start, now;
  __asm__ volatile ("mrs %0, cntfrq_el0" : "=r" (freq));
  if (!freq) probe_reset();
  __asm__ volatile ("mrs %0, cntpct_el0" : "=r" (start));
  do {
    __asm__ volatile ("mrs %0, cntpct_el0" : "=r" (now));
  } while (now - start < freq * seconds);
}

/* Clean written cache lines if the bootloader left the data cache enabled. */
static void publish(const struct surface *s)
{
  uint64_t el, sctlr, ctr;
  __asm__ volatile ("mrs %0, CurrentEL" : "=r" (el));
  if (el == 8) __asm__ volatile ("mrs %0, sctlr_el2" : "=r" (sctlr));
  else __asm__ volatile ("mrs %0, sctlr_el1" : "=r" (sctlr));
  if (sctlr & 4) {
    __asm__ volatile ("mrs %0, ctr_el0" : "=r" (ctr));
    uint64_t line = 4ULL << ((ctr >> 16) & 15);
    uint64_t end = s->base + (uint64_t)(s->height - 1) * s->stride + s->width * 4;
    for (uint64_t p = s->base & ~(line - 1); p < end; p += line)
      __asm__ volatile ("dc cvac, %0" : : "r" (p) : "memory");
  }
  __asm__ volatile ("dsb sy" : : : "memory");
}

static void pattern(const struct surface *s, uint32_t dark)
{
  for (uint32_t y = 0; y < s->height; y++) {
    volatile uint32_t *row = (volatile uint32_t *)(s->base + (uint64_t)y * s->stride);
    for (uint32_t x = 0; x < s->width; x++)
      row[x] = ((x / 120 + y / 120) & 1) ? dark : 0xffffffff;
  }
}

static void text(const struct surface *s, uint32_t row, const char *t)
{
  uint32_t scale = s->width >= 900 ? 3 : s->width >= 600 ? 2 : 1;
  uint32_t x = 12;
  for (; *t && x + 6 * scale < s->width; t++, x += 6 * scale) {
    int g = *t >= '0' && *t <= '9' ? *t - '0' :
            *t >= 'A' && *t <= 'Z' ? *t - 'A' + 10 : -1;
    for (uint32_t y = 0; y < 9 * scale && row + y < s->height; y++) {
      volatile uint32_t *pixels = (volatile uint32_t *)(s->base + (uint64_t)(row + y) * s->stride);
      for (uint32_t dx = 0; dx < 6 * scale; dx++) {
        uint32_t lit = g >= 0 && y / scale < 7 && dx / scale < 5 &&
          (glyphs[g][y / scale] & (1U << (4 - dx / scale)));
        pixels[x + dx] = lit ? 0xffffffff : 0xff000000;
      }
    }
  }
}

static char *append(char *out, const char *in)
{
  while (*in) *out++ = *in++;
  *out = 0;
  return out;
}
static char *hex(char *out, uint32_t value)
{
  for (int shift = 28; shift >= 0; shift -= 4)
    *out++ = "0123456789ABCDEF"[(value >> shift) & 15];
  *out = 0;
  return out;
}

static int candidate(const struct pipe *p, struct surface *s)
{
  uint32_t w = p->size & 65535, h = p->size >> 16;
  uint32_t x = p->xy & 65535, y = p->xy >> 16, stride = p->stride & 65535;
  /* Linear, interleaved 8-bit RGB, four bytes, no YUV/DX/solid-fill/rotation. */
  if ((p->format >> 30) || ((p->format >> 19) & 3) ||
      (p->format & ((1U << 22) | (1U << 15) | (1U << 14) | (1U << 11))) ||
      ((p->format >> 9) & 3) != 3 || (p->format & 63) != 63 || (p->op & 1))
    return 0;
  if (w < 480 || w > 2400 || h < 720 || h > 3200 || (stride & 3) ||
      stride < (x + w) * 4 || stride > 16384 || (p->address & 3)) return 0;
  uint64_t start = p->address + (uint64_t)y * stride + x * 4;
  uint64_t end = start + (uint64_t)(h - 1) * stride + w * 4;
  if (p->address < SPLASH_BASE || start < SPLASH_BASE || end > SPLASH_END) return 0;
  *s = (struct surface){start, w, h, stride};
  return 1;
}

static void report(const struct surface *s, const struct pipe *p, int selected, const char *phase)
{
  /* Repeat the report over the whole buffer to expose cropping/partial updates. */
  for (uint32_t panel = 0; panel + 680 <= s->height; panel += 800) {
    char line[80], *out;
    uint32_t row = panel + 16;
    text(s, row, "CUPID SCANOUT PROBE V001"); row += 32;
    text(s, row, phase); row += 32;
    out = append(line, selected < 0 ? "NO SAFE PIPE" : "SAFE CANDIDATE P");
    if (selected >= 0) { *out++ = '0' + selected; *out = 0; }
    text(s, row, line); row += 32;
    out = append(line, "BASE "); out = hex(out, (uint32_t)s->base);
    out = append(out, " STRIDE "); hex(out, s->stride);
    text(s, row, line); row += 32;
    out = append(line, "WIDTH "); out = hex(out, s->width);
    out = append(out, " HEIGHT "); hex(out, s->height);
    text(s, row, line); row += 32;
    for (int i = 0; i < 8; i++) {
      out = append(line, "P"); *out++ = '0' + i;
      out = append(out, " A "); out = hex(out, p[i].address);
      out = append(out, " S "); out = hex(out, p[i].size);
      out = append(out, " T "); hex(out, p[i].stride);
      text(s, row, line); row += 28;
      out = append(line, "F "); out = hex(out, p[i].format);
      out = append(out, " U "); out = hex(out, p[i].unpack);
      out = append(out, " O "); hex(out, p[i].op);
      text(s, row, line); row += 28;
    }
    text(s, row, "AUTO RESET AFTER LIVE PHASE");
  }
}

void probe_main(void)
{
  struct pipe pipes[8];
  const struct surface assumed = {SPLASH_BASE, 1080, 2400, 4320};
  struct surface live = assumed, trial;
  int selected = -1;
  pattern(&assumed, 0xffff00ff);
  for (uint32_t row = 32; row < assumed.height - 32; row += 400)
    text(&assumed, row, "CUPID ASSUMED LAYOUT CONTROL");
  publish(&assumed);
  delay(4);
  /* An inaccessible register causes a red exception/reset, not a silent hang. */
  for (int i = 0; i < 8; i++) {
    volatile uint32_t *reg = (volatile uint32_t *)(MDSS_BASE + offsets[i]);
    pipes[i] = (struct pipe){reg[0], reg[2], reg[3], reg[5], reg[9], reg[12], reg[13], reg[14]};
    if (candidate(&pipes[i], &trial) &&
        (selected < 0 || (uint64_t)trial.width * trial.height > (uint64_t)live.width * live.height)) {
      selected = i;
      live = trial;
    }
  }
  pattern(&assumed, 0xff202020);
  report(&assumed, pipes, selected, "ASSUMED GEOMETRY REGISTER REPORT");
  publish(&assumed);
  delay(8);
  pattern(&live, 0xff000000);
  report(&live, pipes, selected, selected < 0 ? "FALLBACK NO VALIDATED LIVE BUFFER" : "LIVE CANDIDATE GEOMETRY");
  publish(&live);
  delay(20);
  probe_reset();
}
