.PHONY: help
help:
	@echo "--- help ---"
	@echo "F=[ext4, btrfs, xfs]"
	@echo "I=[baseline, check-kasan, check-ktsan, dart, dart-dev]"
	@echo ""
	@echo "`$(MAKE) -s script/docker.mk docker-help`"
	@echo "`$(MAKE) -s script/build.mk build-help`"
	@echo "`$(MAKE) -s script/spec.mk spec-help`"
	@echo "`$(MAKE) -s script/exec.mk exec-help`"
	@echo "`$(MAKE) -s script/work.mk work-help`"
	@echo "`$(MAKE) -s script/fuzz.mk fuzz-help`"

include script/docker.mk

include script/build.mk

include script/spec.mk

include script/exec.mk

include script/work.mk

include script/fuzz.mk
