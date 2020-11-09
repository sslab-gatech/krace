define racer_build
	$(eval goal := $(patsubst build-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/build.py $(opts) $(args) $(vals)
endef

.PHONY: build-help
build-help:
	@echo "build-: binutils llvm"
	@echo "build-: qemu musl"
	@echo "build-: linux"
	@echo "build-: initramfs"
	@echo "build-: e2fsprogs btrfsprogs xfsprogs"
	@echo "build-: racer"
	@echo "build-: all"

.PHONY: build-binutils
build-binutils:
	$(call racer_build,$@)

.PHONY: build-llvm
build-llvm:
	$(call racer_build,$@)

.PHONY: build-qemu
build-qemu:
	$(call racer_build,$@)

.PHONY: build-musl
build-musl:
	$(call racer_build,$@)

.PHONY: build-linux
build-linux: build-llvm build-racer
	$(call racer_build,$@)

.PHONY: build-initramfs
build-initramfs: build-musl build-linux
	$(call racer_build,$@)

.PHONY: build-e2fsprogs
build-e2fsprogs:
	$(call racer_build,$@)

.PHONY: build-btrfsprogs
build-btrfsprogs:
	$(call racer_build,$@)

.PHONY: build-xfsprogs
build-xfsprogs:
	$(call racer_build,$@)

.PHONY: build-racer
build-racer: build-llvm
	$(call racer_build,$@)

.PHONY: build-all
build-all: \
	build-binutils \
	build-llvm \
	build-qemu \
	build-musl \
	build-linux \
	build-initramfs \
	build-e2fsprogs \
	build-btrfsprogs \
	build-xfsprogs \
	build-racer
