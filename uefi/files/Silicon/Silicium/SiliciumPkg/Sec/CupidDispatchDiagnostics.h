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
  CONST UINTN Scale = 6;
  UINTN X = 36;
  for (UINTN Ch = 0; Text[Ch] && Ch < 28; Ch++, X += 6 * Scale) {
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
      continue;
    }
    for (UINTN Y = 0; Y < 7; Y++) {
      for (UINTN Bit = 0; Bit < 5; Bit++) {
        if (!(CupidTraceGlyphs[Glyph][Y] & (1U << (4 - Bit)))) {
          continue;
        }
        for (UINTN Dy = 0; Dy < Scale; Dy++) {
          for (UINTN Dx = 0; Dx < Scale; Dx++) {
            Fb[(Row + Y * Scale + Dy) * 1080 + X + Bit * Scale + Dx] = Color;
          }
        }
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

STATIC VOID CupidTraceDriver (
  UINTN Sequence, CONST EFI_GUID *Guid, CONST CHAR8 *Phase, EFI_STATUS Status)
{
  volatile UINT32 *Fb = (volatile UINT32 *)0xB8000000ULL;
  CHAR8 Text[29];
  CONST CHAR8 *Name = "UNKNOWN DRIVER";
  for (UINTN Pixel = 0; Pixel < 1080 * 720; Pixel++) {
    Fb[Pixel] = 0x00101010;
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
  CupidTraceText (36, "CUPID DXE TRACE", 0x00FFFFFF);
  CupidTraceText (108, Phase, 0x00FFFF00);
  CupidTraceHex (Text, Sequence, 4);
  CupidTraceText (180, Text, 0x00FFFFFF);
  CupidTraceText (252, Name, 0x0000FFFF);
  CupidTraceHex (Text, Status, 16);
  CupidTraceText (324, Text, 0x00FFFFFF);
  if (Guid != NULL) {
    CupidTraceHex (Text, Guid->Data1, 8);
    Text[8] = '-';
    CupidTraceHex (Text + 9, Guid->Data2, 4);
    Text[13] = '-';
    CupidTraceHex (Text + 14, Guid->Data3, 4);
    CupidTraceText (396, Text, 0x00FFFFFF);
    for (UINTN I = 0; I < 8; I++) {
      CupidTraceHex (Text + 2 * I, Guid->Data4[I], 2);
    }
    CupidTraceText (468, Text, 0x00FFFFFF);
  }
  __asm__ volatile ("dsb sy" : : : "memory");
}
#else
#define CupidTraceDriver(Sequence, Guid, Phase, Status) do { } while (0)
#endif
#endif
