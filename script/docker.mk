define racer_docker
	$(eval goal := $(patsubst docker-%,%,$1))
	$(eval args := $(subst -, ,$(goal)))
	$(eval opts := $(if $(findstring $1,$(MAKECMDGOALS)),$(EXTRA),))
	$(eval vals := $(if $(findstring $1,$(MAKECMDGOALS)),$(VALUE),))
	python3 script/docker.py $(opts) $(args) $(vals)
endef

.PHONY: docker-help
docker-help:
	@echo "docker-: help status mkleaf mkroot"
	@echo "docker-: build-[base]"
	@echo "docker-: start-[base]"
	@echo "docker-: shell-[base]"
	@echo "docker-: reset-[base]"
	@echo "docker-: clean-[base]"

.PHONY: docker-status
docker-status:
	$(call racer_docker,$@)

.PHONY: docker-mkleaf
docker-mkleaf:
	$(call racer_docker,$@)

.PHONY: docker-mkroot
docker-mkroot:
	$(call racer_docker,$@)

.PHONY: docker-build-base
docker-build-base:
	$(call racer_docker,$@)

.PHONY: docker-start-base
docker-start-base:
	$(call racer_docker,$@)

.PHONY: docker-shell-base
docker-shell-base:
	$(call racer_docker,$@)

.PHONY: docker-reset-base
docker-reset-base:
	$(call racer_docker,$@)

.PHONY: docker-clean-base
docker-clean-base:
	$(call racer_docker,$@)
