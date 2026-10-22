/* Cupid-only RAM diagnostics; no firmware protocol, USB or storage dependency. */
#ifndef CUPID_DIAGNOSTICS_H
#define CUPID_DIAGNOSTICS_H

#ifdef CUPID_EARLY_DIAGNOSTICS
STATIC VOID CupidDelay (UINT64 Seconds)
{
  UINT64 Frequency, Start, Now;
  __asm__ volatile ("mrs %0, cntfrq_el0" : "=r" (Frequency));
  __asm__ volatile ("mrs %0, cntpct_el0" : "=r" (Start));
  do {
    __asm__ volatile ("mrs %0, cntpct_el0" : "=r" (Now));
  } while (Now - Start < Frequency * Seconds);
}

STATIC VOID CupidReset (VOID)
{
  register UINT64 X0 __asm__ ("x0") = 0x84000009;
  register UINT64 X1 __asm__ ("x1") = 0;
  register UINT64 X2 __asm__ ("x2") = 0;
  register UINT64 X3 __asm__ ("x3") = 0;
  __asm__ volatile ("smc #0" : "+r" (X0), "+r" (X1), "+r" (X2), "+r" (X3) : : "memory");
  for (;;) {
    __asm__ volatile ("wfe");
  }
}

STATIC UINT32 CupidStopStage (VOID)
{
  volatile UINT32 *Header = (volatile UINT32 *)0xF6000000ULL;
  UINT32 Size = Header[1];
  UINTN Pos = 8;
  if (Header[0] != 0x50554E58 || Size > 0x03FFF000 || Size < 24) {
    return 0;
  }
  while (Pos + 24 <= (UINTN)Size + 8) {
    volatile UINT32 *Entry = (volatile UINT32 *)(0xF6000000ULL + Pos);
    UINT32 Length = Entry[4];
    if (Entry[0] == 0) {
      break;
    }
    if ((UINTN)Length > Size + 8 - Pos - 24) {
      break;
    }
    /* "sec-stop" padded to 16 bytes, followed by a binary little-endian u32. */
    if (Entry[0] == 0x2D636573 && Entry[1] == 0x706F7473 &&
        Entry[2] == 0 && Entry[3] == 0 && Length == 4) {
      return Entry[6];
    }
    Pos += 24 + (((UINTN)Length + 15) & ~(UINTN)15);
  }
  return 0;
}

STATIC VOID CupidEarlyStage (UINT32 Stage)
{
  STATIC CONST UINT32 Colors[] = {
    0x00FF0000, 0x00FFFF00, 0x0000FFFF, 0x0000FF00,
    0x000000FF, 0x00FF00FF, 0x00FFFFFF, 0x00FF8000,
    0x00808080, 0x0080FF00, 0x008000FF, 0x00008080, 0x00FFD700
  };
  volatile UINT32 *Fb = (volatile UINT32 *)0xB8000000ULL;
  UINT32 Color = Colors[Stage < ARRAY_SIZE (Colors) ? Stage : 0];
  for (UINTN Pixel = 0; Pixel < 1080 * 2400; Pixel++) {
    Fb[Pixel] = Color;
  }
  __asm__ volatile ("dsb sy" : : : "memory");
  CupidDelay (1);
  if (Stage == 0 || CupidStopStage () == Stage) {
    CupidDelay (8);
    CupidReset ();
  }
}
#else
#define CupidEarlyStage(Stage) do { } while (0)
#endif
#endif
