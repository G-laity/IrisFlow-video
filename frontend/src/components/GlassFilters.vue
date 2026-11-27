<script setup lang="ts">
/**
 * 全局玻璃滤镜定义（一次挂载，所有 .glass-card 共用）。
 *
 * REFRACT 由 .glass-card__warp 的 backdrop-filter 提供；
 * 本滤镜把 warp 的折射结果按透镜位移图做边缘弯曲 + RGB 色散，
 * 中心用反 mask 保留原始 blurred 背景，内容层不在滤镜内。
 */
import { getGlassLensMap } from "../utils/glassLens";

const lensMap = getGlassLensMap();
</script>

<template>
  <svg
    width="0"
    height="0"
    style="position: absolute; pointer-events: none"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <filter id="glass-lens" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB">
        <feImage
          :href="lensMap"
          x="0"
          y="0"
          width="100%"
          height="100%"
          result="MAP"
          preserveAspectRatio="none"
        />

        <feColorMatrix
          in="MAP"
          type="matrix"
          values="0.3 0.3 0.3 0 0
                  0.3 0.3 0.3 0 0
                  0.3 0.3 0.3 0 0
                  0 0 0 1 0"
          result="EDGE_INTENSITY"
        />
        <feComponentTransfer in="EDGE_INTENSITY" result="EDGE_MASK">
          <feFuncA type="discrete" tableValues="0 0.1 1" />
        </feComponentTransfer>

        <feOffset in="SourceGraphic" dx="0" dy="0" result="CENTER_ORIGINAL" />

        <feDisplacementMap
          in="SourceGraphic"
          in2="MAP"
          scale="70"
          xChannelSelector="R"
          yChannelSelector="B"
          result="RED_DISPLACED"
        />
        <feColorMatrix
          in="RED_DISPLACED"
          type="matrix"
          values="1 0 0 0 0
                  0 0 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="RED_CHANNEL"
        />

        <feDisplacementMap
          in="SourceGraphic"
          in2="MAP"
          scale="63"
          xChannelSelector="R"
          yChannelSelector="B"
          result="GREEN_DISPLACED"
        />
        <feColorMatrix
          in="GREEN_DISPLACED"
          type="matrix"
          values="0 0 0 0 0
                  0 1 0 0 0
                  0 0 0 0 0
                  0 0 0 1 0"
          result="GREEN_CHANNEL"
        />

        <feDisplacementMap
          in="SourceGraphic"
          in2="MAP"
          scale="56"
          xChannelSelector="R"
          yChannelSelector="B"
          result="BLUE_DISPLACED"
        />
        <feColorMatrix
          in="BLUE_DISPLACED"
          type="matrix"
          values="0 0 0 0 0
                  0 0 0 0 0
                  0 0 1 0 0
                  0 0 0 1 0"
          result="BLUE_CHANNEL"
        />

        <feBlend in="GREEN_CHANNEL" in2="BLUE_CHANNEL" mode="screen" result="GB_COMBINED" />
        <feBlend in="RED_CHANNEL" in2="GB_COMBINED" mode="screen" result="RGB_COMBINED" />
        <feGaussianBlur in="RGB_COMBINED" stdDeviation="0.4" result="ABERRATED_BLURRED" />
        <feComposite in="ABERRATED_BLURRED" in2="EDGE_MASK" operator="in" result="EDGE_ABERRATION" />

        <feComponentTransfer in="EDGE_MASK" result="INVERTED_MASK">
          <feFuncA type="table" tableValues="1 0" />
        </feComponentTransfer>
        <feComposite in="CENTER_ORIGINAL" in2="INVERTED_MASK" operator="in" result="CENTER_CLEAN" />
        <feComposite in="EDGE_ABERRATION" in2="CENTER_CLEAN" operator="over" />
      </filter>
    </defs>
  </svg>
</template>
