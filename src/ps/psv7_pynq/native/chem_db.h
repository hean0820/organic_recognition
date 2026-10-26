#ifndef CHEM_DB_H
#define CHEM_DB_H
#include <stddef.h>
#define CHEM_COUNT 22U
typedef struct {
    const char *label, *zh, *en, *formula, *structure, *cas;
    const char *physical, *chemical, *uses, *model;
} Chemical;
extern const Chemical chemicals[CHEM_COUNT];
#endif
