define racer_work
	$(eval goal := $(patsubst work-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/work.py $(opts) $(args) $(vals)
endef

.PHONY: work-help
work-help:
	@echo "work-: prep"

.PHONY: work-prep
work-prep: build-qemu build-linux build-initramfs
	$(call racer_work,$@)