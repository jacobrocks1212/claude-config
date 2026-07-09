---
name: web-audio
description: Fault-tolerant browser audio patterns — AudioContext singleton, preloading, cloneNode rapid-fire, autoplay handling, Web Audio effects. Use when implementing audio playback in web apps.
---

# Web Audio Browser Patterns

Production-tested patterns for fault-tolerant browser audio with zero-lag rapid-fire support.

## Core Principles

### 1. AudioContext Singleton
Create one per page, reuse forever. Browsers limit context instances and creation is expensive.

```typescript
class AudioService {
  private static instance: AudioService;
  private audioContext: AudioContext | null = null;

  static getInstance(): AudioService {
    if (!AudioService.instance) {
      AudioService.instance = new AudioService();
    }
    return AudioService.instance;
  }

  async getContext(): Promise<AudioContext> {
    if (!this.audioContext) {
      this.audioContext = new AudioContext();
    }
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
    }
    return this.audioContext;
  }
}
```

### 2. Preload All Sounds at Startup
Load all sounds during initialization to ensure instant playback. Never load during gameplay.

```typescript
const soundBuffers = new Map<string, AudioBuffer>();

async function preloadSounds(urls: string[]): Promise<void> {
  const context = await AudioService.getInstance().getContext();

  await Promise.all(urls.map(async (url) => {
    const response = await fetch(url);
    const arrayBuffer = await response.arrayBuffer();
    const audioBuffer = await context.decodeAudioData(arrayBuffer);
    soundBuffers.set(url, audioBuffer);
  }));
}
```

### 3. Rapid-Fire with cloneNode
Use `cloneNode()` for instant playable copies instead of triggering new network requests.

```typescript
// For HTML Audio elements
const soundCache = new Map<string, HTMLAudioElement>();

function playSound(url: string): void {
  let audio = soundCache.get(url);
  if (!audio) {
    audio = new Audio(url);
    soundCache.set(url, audio);
  }

  // Clone for overlapping sounds
  const clone = audio.cloneNode() as HTMLAudioElement;
  clone.play().catch(() => {});
}
```

### 4. Sound Cancellation for Non-Overlapping Sounds
Cancel previous instances for UI feedback and voice to prevent audio pile-up.

```typescript
const activeSounds = new Map<string, AudioBufferSourceNode>();

function playSoundExclusive(id: string, buffer: AudioBuffer): void {
  // Stop previous instance
  const existing = activeSounds.get(id);
  if (existing) {
    existing.stop();
  }

  const context = AudioService.getInstance().getContext();
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  source.start();

  activeSounds.set(id, source);
  source.onended = () => activeSounds.delete(id);
}
```

### 5. Autoplay Handling
Always include silent `.catch(() => {})` on every `.play()` call to handle browser autoplay policies.

```typescript
// Always handle autoplay rejection gracefully
audio.play().catch(() => {
  // Silent catch - browser blocked autoplay
  // User interaction will resume later
});

// Or with user interaction
document.addEventListener('click', async () => {
  const context = await AudioService.getInstance().getContext();
  // Context is now guaranteed to be running
}, { once: true });
```

## Advanced Features

### Sidechain Ducking
Reduce music volume when sound effects play.

```typescript
function setupDucking(musicGain: GainNode, duckAmount = 0.3): {
  duck: () => void;
  unduck: () => void;
} {
  return {
    duck: () => {
      musicGain.gain.linearRampToValueAtTime(duckAmount, audioContext.currentTime + 0.1);
    },
    unduck: () => {
      musicGain.gain.linearRampToValueAtTime(1.0, audioContext.currentTime + 0.3);
    }
  };
}
```

### Convolver Reverb
Apply reverb using impulse response files.

```typescript
async function createReverb(impulseUrl: string): Promise<ConvolverNode> {
  const context = await AudioService.getInstance().getContext();
  const convolver = context.createConvolver();

  const response = await fetch(impulseUrl);
  const arrayBuffer = await response.arrayBuffer();
  convolver.buffer = await context.decodeAudioData(arrayBuffer);

  return convolver;
}
```

## Volume Hierarchy

Implement sound type-based volume levels for balanced audio:

| Sound Type | Volume Range |
|------------|--------------|
| Hover/Click | 0.2 - 0.3 |
| Success/Error | 0.3 - 0.5 |
| Major Events | 0.7 - 0.8 |
| Background Music | 0.15 - 0.25 |

```typescript
const VOLUME_LEVELS = {
  ui: 0.25,
  feedback: 0.4,
  event: 0.75,
  music: 0.2,
} as const;

function playWithVolume(buffer: AudioBuffer, type: keyof typeof VOLUME_LEVELS): void {
  const source = context.createBufferSource();
  const gainNode = context.createGain();

  source.buffer = buffer;
  gainNode.gain.value = VOLUME_LEVELS[type];

  source.connect(gainNode).connect(context.destination);
  source.start();
}
```

## Accessibility

### Respect Reduced Motion
```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function playUISound(buffer: AudioBuffer): void {
  if (prefersReducedMotion) return;
  // Play sound
}
```

### Persistent Audio Settings
```typescript
const AUDIO_PREFS_KEY = 'audio-preferences';

interface AudioPrefs {
  masterVolume: number;
  musicEnabled: boolean;
  sfxEnabled: boolean;
}

function saveAudioPrefs(prefs: AudioPrefs): void {
  localStorage.setItem(AUDIO_PREFS_KEY, JSON.stringify(prefs));
}

function loadAudioPrefs(): AudioPrefs {
  const saved = localStorage.getItem(AUDIO_PREFS_KEY);
  return saved ? JSON.parse(saved) : {
    masterVolume: 1.0,
    musicEnabled: true,
    sfxEnabled: true,
  };
}
```

## Complete AudioService Example

```typescript
class AudioService {
  private static instance: AudioService;
  private audioContext: AudioContext | null = null;
  private buffers = new Map<string, AudioBuffer>();
  private activeSources = new Map<string, AudioBufferSourceNode>();
  private masterGain: GainNode | null = null;

  static getInstance(): AudioService {
    if (!AudioService.instance) {
      AudioService.instance = new AudioService();
    }
    return AudioService.instance;
  }

  async init(): Promise<void> {
    this.audioContext = new AudioContext();
    this.masterGain = this.audioContext.createGain();
    this.masterGain.connect(this.audioContext.destination);
  }

  async preload(sounds: Record<string, string>): Promise<void> {
    if (!this.audioContext) await this.init();

    const entries = Object.entries(sounds);
    await Promise.all(entries.map(async ([key, url]) => {
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const buffer = await this.audioContext!.decodeAudioData(arrayBuffer);
      this.buffers.set(key, buffer);
    }));
  }

  play(key: string, options: { exclusive?: boolean; volume?: number } = {}): void {
    const buffer = this.buffers.get(key);
    if (!buffer || !this.audioContext || !this.masterGain) return;

    if (options.exclusive) {
      this.activeSources.get(key)?.stop();
    }

    const source = this.audioContext.createBufferSource();
    const gain = this.audioContext.createGain();

    source.buffer = buffer;
    gain.gain.value = options.volume ?? 1.0;

    source.connect(gain).connect(this.masterGain);
    source.start();

    if (options.exclusive) {
      this.activeSources.set(key, source);
      source.onended = () => this.activeSources.delete(key);
    }
  }

  setMasterVolume(volume: number): void {
    if (this.masterGain) {
      this.masterGain.gain.value = Math.max(0, Math.min(1, volume));
    }
  }
}
```
