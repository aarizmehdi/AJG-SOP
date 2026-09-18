import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../api/client';
import { speechTranscriptionSchema } from '../../types/speech';
import type { Language } from '../language/language-context';

export type VoiceState = 'idle' | 'listening' | 'transcribing' | 'error';

export function useVoiceInput({
  enabled,
  language,
  onTranscript,
}: {
  enabled: boolean;
  language: Language;
  onTranscript: (transcript: string) => void;
}) {
  const [state, setState] = useState<VoiceState>('idle');
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const cancelled = useRef(false);

  const release = useCallback(() => {
    stream.current?.getTracks().forEach((track) => {
      track.stop();
    });
    stream.current = null;
    recorder.current = null;
    chunks.current = [];
  }, []);

  const cancel = useCallback(() => {
    cancelled.current = true;
    if (recorder.current?.state === 'recording') recorder.current.stop();
    else release();
    setState('idle');
  }, [release]);

  const start = useCallback(async () => {
    if (!enabled || state !== 'idle') return;
    try {
      cancelled.current = false;
      chunks.current = [];
      const recordingStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      stream.current = recordingStream;
      const nextRecorder = new MediaRecorder(recordingStream);
      recorder.current = nextRecorder;
      nextRecorder.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      nextRecorder.onstop = () => {
        if (cancelled.current) {
          release();
          return;
        }
        const audio = new Blob(chunks.current, {
          type: nextRecorder.mimeType || 'audio/webm',
        });
        release();
        setState('transcribing');
        const body = new FormData();
        body.append('audio', audio, 'voice-question.webm');
        void apiRequest(
          `/speech/transcribe?response_language=${encodeURIComponent(language)}`,
          speechTranscriptionSchema,
          { method: 'POST', body },
        )
          .then((result) => {
            onTranscript(result.normalized_transcript);
            setState('idle');
          })
          .catch(() => {
            setState('error');
          });
      };
      nextRecorder.start();
      setState('listening');
    } catch {
      release();
      setState('error');
    }
  }, [enabled, language, onTranscript, release, state]);

  const stop = useCallback(() => {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }, []);

  useEffect(() => {
    if (state !== 'listening') return;
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') cancel();
    };
    document.addEventListener('keydown', onEscape);
    return () => {
      document.removeEventListener('keydown', onEscape);
    };
  }, [cancel, state]);

  useEffect(
    () => () => {
      cancelled.current = true;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      release();
    },
    [release],
  );

  return { state, start, stop, cancel };
}
