# ADR 0002: Verified answer release

**Status:** accepted

The assistant retrieves authorized canonical evidence, checks answerability, generates a structured candidate, validates citation membership and source locations, and runs deterministic grounding checks. Only the resulting `VerifiedAnswer` may be stored or returned. Realtime events expose stage names and the final verified payload; model tokens are never streamed.
