define racer_exec
	$(eval goal := $(patsubst exec-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/exec.py $(opts) $(args) $(vals)
endef

.PHONY: exec-help
exec-help:
	@echo "exec-: test"

.PHONY: exec-test
exec-test: build-qemu build-linux build-initramfs
	$(call racer_exec,$@)