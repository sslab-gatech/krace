define racer_spec
	$(eval goal := $(patsubst spec-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/spec.py $(opts) $(args) $(vals)
endef

.PHONY: spec-help
spec-help:
	@echo "spec-: extract"
	@echo "spec-: compose"

.PHONY: spec-extract
spec-extract: build-linux build-musl
	$(call racer_spec,$@)

.PHONY: spec-compose
spec-compose: spec-extract
	$(call racer_spec,$@)