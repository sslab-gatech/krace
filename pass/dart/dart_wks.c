#include "dart.h"

/* shared info */
unsigned long *g_cov_cfg_edge = NULL;
unsigned long *g_cov_dfg_edge = NULL;
unsigned long *g_cov_alias_inst = NULL;

/* private info */
struct dart_rtinfo *g_rtinfo = NULL;
struct dart_rtrace *g_rtrace = NULL;