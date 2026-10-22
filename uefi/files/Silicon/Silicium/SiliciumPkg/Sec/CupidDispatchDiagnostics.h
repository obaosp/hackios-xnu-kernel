/* Cupid RAM-only DXE driver trace. No console, allocation, USB, or storage. */
#ifndef CUPID_DISPATCH_DIAGNOSTICS_H
#define CUPID_DISPATCH_DIAGNOSTICS_H

#ifdef CUPID_EARLY_DIAGNOSTICS
#include "CupidDriverNames.h"

STATIC CONST UINT8 CupidTraceGlyphs[][7] = {
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
  {17,17,10,4,4,4,4}, {31,1,2,4,8,16,31},
  {0,0,0,31,0,0,0}, {0,4,4,0,4,4,0}
};

STATIC VOID CupidTraceText (UINTN Row, CONST CHAR8 *Text, UINT32 Color)
{
  volatile UINT32 *Fb = (volatile UINT32 *)0xB8000000ULL;
  CONST UINTN Scale = 4;
  UINTN X = 12;
  for (UINTN Ch = 0; Text[Ch] && Ch < 40; Ch++, X += 6 * Scale) {
    UINT8 C = (UINT8)Text[Ch];
    if (C >= 'a' && C <= 'z') {
      C -= 'a' - 'A';
    }
    UINTN Glyph;
    if (C >= '0' && C <= '9') {
      Glyph = C - '0';
    } else if (C >= 'A' && C <= 'Z') {
      Glyph = C - 'A' + 10;
    } else if (C == '-') {
      Glyph = 36;
    } else if (C == ':') {
      Glyph = 37;
    } else {
      Glyph = ARRAY_SIZE (CupidTraceGlyphs);
    }
    for (UINTN Y = 0; Y < 9 * Scale; Y++) {
      for (UINTN Dx = 0; Dx < 6 * Scale; Dx++) {
        BOOLEAN Lit = Glyph < ARRAY_SIZE (CupidTraceGlyphs) && Y / Scale < 7 &&
          Dx / Scale < 5 && (CupidTraceGlyphs[Glyph][Y / Scale] & (1U << (4 - Dx / Scale)));
        Fb[(Row + Y) * 1080 + X + Dx] = Lit ? Color : 0xFF000000;
      }
    }
  }
}

STATIC VOID CupidTraceHex (CHAR8 *Text, UINT64 Value, UINTN Digits)
{
  STATIC CONST CHAR8 Hex[] = "0123456789ABCDEF";
  for (UINTN I = 0; I < Digits; I++) {
    Text[Digits - I - 1] = Hex[Value & 15];
    Value >>= 4;
  }
  Text[Digits] = 0;
}

STATIC __attribute__((noinline)) VOID CupidTraceDriver (
  UINTN Sequence, CONST EFI_GUID *Guid, CONST CHAR8 *Phase, EFI_STATUS Status)
{
  volatile UINT32 *Fb = (volatile UINT32 *)0xB8000000ULL;
  CHAR8 Text[41];
  CONST CHAR8 *Name = "UNKNOWN DRIVER";
  for (UINTN Pixel = 0; Pixel < 1080 * 2400; Pixel++) {
    Fb[Pixel] = 0xFF101030;
  }
  if (Guid != NULL) {
    for (UINTN I = 0; I < ARRAY_SIZE (CupidDriverNames); I++) {
      CONST EFI_GUID *Candidate = &CupidDriverNames[I].Guid;
      BOOLEAN Same = TRUE;
      CONST UINT8 *A = (CONST UINT8 *)Guid;
      CONST UINT8 *B = (CONST UINT8 *)Candidate;
      for (UINTN Byte = 0; Byte < sizeof (EFI_GUID); Byte++) {
        if (A[Byte] != B[Byte]) {
          Same = FALSE;
          break;
        }
      }
      if (Same) {
        Name = CupidDriverNames[I].Name;
        break;
      }
    }
  }
  for (UINTN Panel = 0; Panel < 2400; Panel += 800) {
    CupidTraceText (Panel + 32, "CUPID DXE TRACE V007", 0xFFFFFFFF);
    CupidTraceText (Panel + 88, Phase, 0xFFFFFFFF);
    CupidTraceHex (Text, Sequence, 4);
    CupidTraceText (Panel + 144, Text, 0xFFFFFFFF);
    CupidTraceText (Panel + 200, Name, 0xFFFFFFFF);
    CupidTraceHex (Text, Status, 16);
    CupidTraceText (Panel + 256, Text, 0xFFFFFFFF);
    if (Guid != NULL) {
      CupidTraceHex (Text, Guid->Data1, 8);
      Text[8] = '-';
      CupidTraceHex (Text + 9, Guid->Data2, 4);
      Text[13] = '-';
      CupidTraceHex (Text + 14, Guid->Data3, 4);
      CupidTraceText (Panel + 312, Text, 0xFFFFFFFF);
      for (UINTN I = 0; I < 8; I++) {
        CupidTraceHex (Text + 2 * I, Guid->Data4[I], 2);
      }
      CupidTraceText (Panel + 368, Text, 0xFFFFFFFF);
    }
    UINT64 State;
    __asm__ volatile ("mrs %0, daif" : "=r" (State));
    CupidTraceHex (Text, State, 4);
    Text[4] = ' ';
    __asm__ volatile ("mrs %0, CurrentEL" : "=r" (State));
    CupidTraceHex (Text + 5, State, 4);
    CupidTraceText (Panel + 424, Text, 0xFFFFFFFF);
  }
  /* Full fills alone do not show whether glyph stores reached scanout. */
  UINT64 Ctr;
  __asm__ volatile ("mrs %0, ctr_el0" : "=r" (Ctr));
  UINTN Line = (UINTN)4 << ((Ctr >> 16) & 15);
  for (UINTN Address = 0xB8000000ULL; Address < 0xB89E3400ULL; Address += Line) {
    __asm__ volatile ("dc cvac, %0" : : "r" (Address) : "memory");
  }
  __asm__ volatile ("dsb sy" : : : "memory");
}
#else
#define CupidTraceDriver(Sequence, Guid, Phase, Status) do { } while (0)
#endif
#endif
