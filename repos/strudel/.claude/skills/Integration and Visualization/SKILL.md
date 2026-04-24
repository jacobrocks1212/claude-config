---
name: strudel-integration-and-visualization
description: Provides guidance for integrating Strudel with external systems and for using its visual feedback capabilities. This skill covers topics such as MIDI, OSC, Hydra, and the various visualization tools available in Strudel.
version: 1.0.0
allowed-tools: ["Read", "Grep"]
---

# Integration and Visualization Skill

This skill provides guidance for integrating Strudel with external systems and for using its visual feedback capabilities. It is designed for users who want to extend the capabilities of Strudel by connecting it to other software and hardware, and for those who want to take advantage of its powerful visualization tools.

## Overview

Strudel is a versatile tool that can be integrated with a wide range of external systems, from hardware synthesizers to visual programming environments. It also includes a number of built-in visualization tools that can help you to better understand and interact with your musical patterns.

**Primary Directive:** When integrating Strudel with external systems, be sure to read the relevant documentation to ensure that you are using the correct protocols and settings. When using the visualization tools, experiment with the different options to find the ones that are most useful for your workflow.

## Key Concepts

### Input and Output
Strudel can send and receive data from external systems using a variety of protocols, including MIDI, OSC, and MQTT. This allows you to control hardware synthesizers, interact with other music software, and even control physical devices. For more information, see `input-output.md`.

### Input Devices
Strudel can be controlled by a variety of input devices, including MIDI controllers and gamepads. This allows you to interact with your musical patterns in a more tactile and expressive way. Learn more in `input-devices.md`.

### Hydra
Hydra is a live coding environment for creating visuals. Strudel can be integrated with Hydra, allowing you to create audio-reactive visuals and to control your music with visual patterns. For more information, see `hydra.md`.

### Visual Feedback
Strudel includes a number of built-in visualization tools that can help you to better understand your musical patterns. These include a piano roll, a spiral visualizer, and an oscilloscope. Learn more in `visual-feedback.md`.

### Signals
Signals are continuous patterns that can be used to control the parameters of your sounds and effects. They can also be used to create interesting visualizations. For a list of available signals, see `signals.md`.

### Metadata
Strudel allows you to add metadata to your compositions, such as the title, author, and license. This can be useful for organizing your work and for sharing it with others. Learn more in `metadata.md`.

## Development Guidelines

1.  **Start with a Simple Integration**: If you are new to integrating Strudel with external systems, start with a simple setup, such as controlling a single synthesizer with MIDI.
2.  **Explore the Visualization Tools**: The visualization tools can be a great way to get a better understanding of your musical patterns. Spend some time exploring the different options to see what they can do.
3.  **Get Creative**: The integration and visualization capabilities of Strudel open up a world of creative possibilities. Don't be afraid to experiment and try new things.

## When to Reference Additional Files

-   For information on connecting Strudel to external systems, see `input-output.md`.
-   To learn about using input devices with Strudel, refer to `input-devices.md`.
-   For information on integrating Strudel with Hydra, see `hydra.md`.
-   To learn about the built-in visualization tools, see `visual-feedback.md`.
-   For a list of available signals, see `signals.md`.
-   To learn how to add metadata to your compositions, see `metadata.md`.
