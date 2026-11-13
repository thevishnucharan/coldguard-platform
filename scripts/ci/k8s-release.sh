#!/usr/bin/env bash
# Phase (gated): push images to a registry and deploy the production overlay with the exact
# image tag built by this pipeline.
#   REGISTRY=myregistry.example.com/coldguard IMAGE_TAG=<sha> KUBE_CONTEXT=<prod-context> \
#   ALLOW_REMOTE_CONTEXT=1 scripts/ci/k8s-release.sh [push|deploy|all]
# The production `coldguard-secrets` Secret must already exist (external secret store); this
# script never creates secrets.
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
: "${REGISTRY:?set REGISTRY (e.g. registry.example.com/coldguard)}"
what=${1:-all}

if [ "$what" = push ] || [ "$what" = all ]; then
  for img in coldguard-backend coldguard-frontend coldguard-simulator; do
    docker tag "$img:$IMAGE_TAG" "$REGISTRY/$img:$IMAGE_TAG"
    docker push "$REGISTRY/$img:$IMAGE_TAG"
  done
  ok "pushed $REGISTRY/*:$IMAGE_TAG"
fi

if [ "$what" = deploy ] || [ "$what" = all ]; then
  : "${KUBE_CONTEXT:?set KUBE_CONTEXT for the production cluster}"
  guard_kube_context "$KUBE_CONTEXT"
  K=(kubectl --context "$KUBE_CONTEXT")
  "${K[@]}" -n coldguard get secret coldguard-secrets >/dev/null || fail "coldguard-secrets missing in the target cluster"
  REL="$ROOT/build/k8s-release"; rm -rf "$REL"; mkdir -p "$REL"
  cat >"$REL/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [../../infrastructure/k8s/overlays/production]
images:
  - { name: REGISTRY/coldguard-backend, newName: $REGISTRY/coldguard-backend, newTag: "$IMAGE_TAG" }
  - { name: REGISTRY/coldguard-frontend, newName: $REGISTRY/coldguard-frontend, newTag: "$IMAGE_TAG" }
EOF
  "${K[@]}" -n coldguard delete job coldguard-migrate --ignore-not-found
  "${K[@]}" apply -k "$REL"
  "${K[@]}" -n coldguard wait --for=condition=complete job/coldguard-migrate --timeout=900s
  for d in backend worker frontend; do "${K[@]}" -n coldguard rollout status "deploy/$d" --timeout=600s; done
  ok "production rollout complete ($IMAGE_TAG)"
fi
