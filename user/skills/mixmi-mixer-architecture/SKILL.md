---
name: mixmi-mixer-architecture
description: Mixer-system architecture reference — audio routing, recording, internals with Tone.js/Web Audio. Use when building DJ interfaces or dual-deck mixers.
---

# DJ Mixer Architecture Reference

Complete technical reference for professional mixer systems using Tone.js and Web Audio API.

## Overview

A dual-deck DJ interface built with:
- **Tone.js** for professional audio processing and effects
- **Web Audio API** for low-level audio routing
- **MediaRecorder API** for live mix recording
- **Canvas API** for waveform visualization
- **requestAnimationFrame** for smooth playhead updates

## Architecture Principles

1. **Professional Audio Quality:** No quality loss, proper gain staging, clean signal flow
2. **Real-time Performance:** 60fps waveform updates, instant FX response
3. **Memory Safety:** Proper cleanup, no leaks, stable for extended sessions
4. **Modular Design:** Decks, FX, controls are independent, reusable components

## Audio Signal Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         DECK A                                  │
│  Audio File → Tone.Player → Filter → Reverb → Delay → Gain ───┐│
└─────────────────────────────────────────────────────────────────┘│
                                                                   │
                        ├─────────────→ Crossfader ←──────────────┤
                                             ↓
┌─────────────────────────────────────────────────────────────────┐│
│                         DECK B                                  ││
│  Audio File → Tone.Player → Filter → Reverb → Delay → Gain ───┘│
└─────────────────────────────────────────────────────────────────┘
                                             ↓
                                       Master Gain
                                             ↓
                              AudioContext Destination (speakers)
                                             ↓
                         MediaStreamAudioDestinationNode (recording)
```

## State Management

```typescript
interface SimplifiedMixerState {
  deckA: DeckState;
  deckB: DeckState;
  masterBPM: number;              // Global tempo (default 120)
  crossfaderPosition: number;     // 0-100 (0=A only, 50=center, 100=B only)
  syncActive: boolean;            // Master sync on/off
}

interface DeckState {
  track: Track | null;
  playing: boolean;
  audioState?: any;               // Tone.js player state
  audioControls?: any;            // Playback controls
  loading?: boolean;
  loopEnabled: boolean;
  loopLength: number;             // 2, 4, 8, 16 bars
  loopPosition: number;           // Which loop section (0, 1, 2...)
  boostLevel: number;             // 0=off, 1=gentle, 2=aggressive
}
```

## Tone.js Integration

### Audio Chain Creation

```typescript
import * as Tone from 'tone';

// Start audio context on user interaction
const startAudio = async () => {
  await Tone.start();
};

// Create audio chain for deck
const createDeckAudioChain = (audioUrl: string) => {
  const player = new Tone.Player(audioUrl);
  const filter = new Tone.Filter(20000, 'lowpass');
  const reverb = new Tone.Reverb(2.0);
  const delay = new Tone.FeedbackDelay('8n', 0.5);
  const gain = new Tone.Gain(1.0);

  player
    .connect(filter)
    .connect(reverb)
    .connect(delay)
    .connect(gain)
    .connect(crossfaderGain);

  return { player, filter, reverb, delay, gain };
};
```

### Playback Control

```typescript
// Play/pause
if (playing) {
  player.start();
} else {
  player.stop();
}

// Loop configuration
player.loop = true;
player.loopStart = loopPosition * loopDuration;
player.loopEnd = (loopPosition + 1) * loopDuration;

// BPM sync (adjust playback rate)
const ratio = masterBPM / track.bpm;
player.playbackRate = ratio;
```

## Loop Implementation

```typescript
// Calculate loop duration based on BPM and bar count
const beatsPerLoop = loopLength * 4;  // 4 beats per bar
const secondsPerBeat = 60 / bpm;
const loopDuration = beatsPerLoop * secondsPerBeat;

// Example: 8-bar loop at 120 BPM = 16 seconds

// Loop position control
const setLoopPosition = (position: number) => {
  const startTime = position * loopDuration;
  const endTime = (position + 1) * loopDuration;

  player.loopStart = startTime;
  player.loopEnd = endTime;

  if (player.state === 'started') {
    player.seek(startTime);
  }
};
```

## BPM Sync Engine

```typescript
class SimpleLoopSync {
  private masterBPM: number = 120;

  setMasterBPM(bpm: number) {
    this.masterBPM = bpm;
    this.syncAllDecks();
  }

  syncDeck(player: Tone.Player, originalBPM: number) {
    const ratio = this.masterBPM / originalBPM;
    player.playbackRate = ratio;
  }
}
```

## Crossfader Mixing

```typescript
const crossfaderGainA = (100 - crossfaderPosition) / 100;
const crossfaderGainB = crossfaderPosition / 100;

// Position 0:   A=1.0, B=0.0 (A only)
// Position 50:  A=0.5, B=0.5 (center)
// Position 100: A=0.0, B=1.0 (B only)
```

## Recording Pipeline

```typescript
// Create destination node for recording
const mixerDestination = Tone.context.createMediaStreamDestination();
masterGainNode.connect(mixerDestination);

// Create MediaRecorder
const mediaRecorder = new MediaRecorder(mixerDestination.stream, {
  mimeType: 'audio/webm;codecs=opus',
  audioBitsPerSecond: 128000
});

// Capture chunks
const audioChunks: BlobPart[] = [];
mediaRecorder.ondataavailable = (e) => {
  if (e.data.size > 0) {
    audioChunks.push(e.data);
  }
};

// Stop & Download
mediaRecorder.onstop = () => {
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  const audioUrl = URL.createObjectURL(audioBlob);

  const a = document.createElement('a');
  a.href = audioUrl;
  a.download = `mix_${Date.now()}.webm`;
  a.click();

  URL.revokeObjectURL(audioUrl);
};
```

## Memory Management (Critical)

### Problem 1: Tone.js Objects Not Disposed

```typescript
// BEFORE: Memory leak
const loadTrack = (track: Track) => {
  const player = new Tone.Player(track.audioUrl);
  setDeckAPlayer(player);  // Previous player never disposed
};

// AFTER: Proper cleanup
const loadTrack = (track: Track) => {
  if (deckAPlayer) {
    deckAPlayer.stop();
    deckAPlayer.disconnect();
    deckAPlayer.dispose();
  }
  const player = new Tone.Player(track.audioUrl);
  setDeckAPlayer(player);
};

// Component unmount cleanup
useEffect(() => {
  return () => {
    deckAPlayer?.stop();
    deckAPlayer?.disconnect();
    deckAPlayer?.dispose();
  };
}, []);
```

### Problem 2: Leaked Timeouts

```typescript
// Track and cleanup timeouts
const timeoutsRef = useRef<Set<NodeJS.Timeout>>(new Set());

const scheduleRetry = () => {
  const timeout = setTimeout(() => {/* retry */}, 100);
  timeoutsRef.current.add(timeout);
};

useEffect(() => {
  return () => {
    timeoutsRef.current.forEach(t => clearTimeout(t));
    timeoutsRef.current.clear();
  };
}, []);
```

### Problem 3: Animation Frame Not Canceled

```typescript
const animationFrameRef = useRef<number | null>(null);

const animate = () => {
  animationFrameRef.current = requestAnimationFrame(animate);
};

useEffect(() => {
  animationFrameRef.current = requestAnimationFrame(animate);
  return () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
  };
}, []);
```

## Waveform Display

```typescript
const drawWaveform = (
  canvas: HTMLCanvasElement,
  audioBuffer: AudioBuffer,
  currentTime: number,
  duration: number
) => {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const { width, height } = canvas;
  ctx.clearRect(0, 0, width, height);

  const data = audioBuffer.getChannelData(0);
  const step = Math.ceil(data.length / width);
  const amp = height / 2;

  ctx.beginPath();
  for (let i = 0; i < width; i++) {
    const slice = data.slice(i * step, (i + 1) * step);
    const min = Math.min(...slice);
    const max = Math.max(...slice);
    ctx.moveTo(i, amp * (1 + min));
    ctx.lineTo(i, amp * (1 + max));
  }
  ctx.strokeStyle = '#81E4F2';
  ctx.stroke();

  // Playhead
  const playheadX = (currentTime / duration) * width;
  ctx.beginPath();
  ctx.moveTo(playheadX, 0);
  ctx.lineTo(playheadX, height);
  ctx.strokeStyle = '#FFE4B5';
  ctx.lineWidth = 2;
  ctx.stroke();
};
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Space | Play/Pause Deck A |
| Shift+Space | Play/Pause Deck B |
| ArrowUp/Down | Increment/Decrement BPM |
| S | Toggle Sync |
| R | Start/Stop Recording |
| L / Shift+L | Toggle Loop (A/B) |
| [ / ] | Previous/Next Loop Position |
| A / B / C | Crossfader to A/B/Center |

## FX Connection Strategy

```typescript
const connectDeckToFX = async (
  player: Tone.Player,
  fxRef: React.RefObject<FXElement>,
  retryCount = 0
): Promise<void> => {
  const maxRetries = 50;
  const retryDelay = 100;

  if (!fxRef.current?.audioInput) {
    if (retryCount < maxRetries) {
      await new Promise(resolve => setTimeout(resolve, retryDelay));
      return connectDeckToFX(player, fxRef, retryCount + 1);
    }
    console.warn('FX connection failed after max retries');
    return;
  }

  player.connect(fxRef.current.audioInput);
  fxRef.current.audioOutput?.connect(crossfaderGain);
};
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No audio playback | Ensure `await Tone.start()` called after user interaction |
| Sync not working | Verify `syncEngine.setMasterBPM()` is called |
| Recording produces no file | Check master gain connected to MediaStreamDestination |
| FX not working | Check FX refs are connected, look for retry warnings |
| Waveform not updating | Verify animation frame is running and refs updating |
