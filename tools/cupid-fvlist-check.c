#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t UINT8;
typedef uint64_t UINT64;
typedef uintptr_t UINTN;
#define CUPID_STOCK_FVLIST 1
#include "Include/FvList.h"
int main(void) {
  _Static_assert(FV_LIST_ALLOCATION_SIZE == 0x210, "stock allocation");
  UINT8 *allocation = calloc(1, FV_LIST_ALLOCATION_SIZE);
  UINTN *list = (UINTN *)allocation;
  for (unsigned i=0; i<8; i++) FV_LIST_LOCK_HANDLE(list,i) = 0x12340000ULL+i;
  for (unsigned pos=0; pos<0x210; pos++) {
    UINT8 expected=0;
    for (unsigned i=0; i<8; i++) {
      unsigned offset=0x18+i*0x40;
      if(pos>=offset && pos<offset+8) expected=(0x12340000ULL+i)>>((pos-offset)*8);
    }
    assert(allocation[pos]==expected);
  }
  /* Stock lookup returns name-0x18; stock lock use is at entry+0x10. */
  for(unsigned i=0;i<8;i++) {
    UINT8 *entry=allocation+0x20+i*0x40-0x18;
    UINT64 lock;
    memcpy(&lock,entry+0x10,8);
    assert(lock==0x12340000ULL+i);
  }
  free(allocation);
}
