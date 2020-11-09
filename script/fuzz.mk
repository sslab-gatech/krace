define racer_fuzz
	$(eval goal := $(patsubst fuzz-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/fuzz.py $(opts) $(args) $(vals)
endef

.PHONY: fuzz-help
fuzz-help:
	@echo "fuzz-: launch"
	@echo "fuzz-: probe"
	@echo "fuzz-: validate"

.PHONY: fuzz-launch
fuzz-launch: build-qemu build-linux build-initramfs spec-compose
	$(call racer_fuzz,$@)

.PHONY: fuzz-probe
fuzz-probe: build-qemu build-linux build-initramfs spec-compose
	$(call racer_fuzz,$@)

.PHONY: fuzz-validate
fuzz-validate: build-qemu build-linux build-initramfs spec-compose
	$(call racer_fuzz,$@)