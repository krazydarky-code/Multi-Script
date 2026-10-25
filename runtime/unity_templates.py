# SPDX-License-Identifier: GPL-3.0-or-later
"""MonoBehaviour templates for ms_unity_gameplay_kit. Plain C#, no packages needed beyond what a new Unity project has.
Every script is compiled in the test-suite against real UnityEngine assemblies (legacy input + a stubbed Input System)."""

CORE = r'''using System;
using System.Collections.Generic;
using UnityEngine;
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
using UnityEngine.InputSystem;
#endif

/// <summary>Input facade that works with the old Input Manager and the new Input System package.</summary>
public static class MSInput
{
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
    public static Vector2 Move()
    {
        Vector2 v = Vector2.zero;
        var kb = Keyboard.current;
        if (kb != null)
        {
            if (kb.aKey.isPressed || kb.leftArrowKey.isPressed) v.x -= 1f;
            if (kb.dKey.isPressed || kb.rightArrowKey.isPressed) v.x += 1f;
            if (kb.sKey.isPressed || kb.downArrowKey.isPressed) v.y -= 1f;
            if (kb.wKey.isPressed || kb.upArrowKey.isPressed) v.y += 1f;
        }
        var gp = Gamepad.current;
        if (gp != null) { var s = gp.leftStick.ReadValue(); if (s.sqrMagnitude > 0.04f) v = s; }
        return Vector2.ClampMagnitude(v, 1f);
    }
    public static Vector2 Look()
    {
        Vector2 v = Vector2.zero;
        if (Mouse.current != null) v = Mouse.current.delta.ReadValue() * 0.05f;
        if (Gamepad.current != null) v += Gamepad.current.rightStick.ReadValue() * 2.5f;
        return v;
    }
    public static bool JumpDown() { return (Keyboard.current != null && Keyboard.current.spaceKey.wasPressedThisFrame) || (Gamepad.current != null && Gamepad.current.buttonSouth.wasPressedThisFrame); }
    public static bool JumpHeld() { return (Keyboard.current != null && Keyboard.current.spaceKey.isPressed) || (Gamepad.current != null && Gamepad.current.buttonSouth.isPressed); }
    public static bool Sprint() { return (Keyboard.current != null && Keyboard.current.leftShiftKey.isPressed) || (Gamepad.current != null && Gamepad.current.leftStickButton.isPressed); }
    public static bool InteractDown() { return (Keyboard.current != null && Keyboard.current.eKey.wasPressedThisFrame) || (Gamepad.current != null && Gamepad.current.buttonWest.wasPressedThisFrame); }
    public static bool FireDown() { return (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame) || (Gamepad.current != null && Gamepad.current.rightTrigger.wasPressedThisFrame); }
    public static bool FireHeld() { return (Mouse.current != null && Mouse.current.leftButton.isPressed) || (Gamepad.current != null && Gamepad.current.rightTrigger.isPressed); }
    public static bool PauseDown() { return (Keyboard.current != null && Keyboard.current.escapeKey.wasPressedThisFrame) || (Gamepad.current != null && Gamepad.current.startButton.wasPressedThisFrame); }
#else
    public static Vector2 Move() { return Vector2.ClampMagnitude(new Vector2(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical")), 1f); }
    public static Vector2 Look() { return new Vector2(Input.GetAxis("Mouse X"), Input.GetAxis("Mouse Y")) * 2f; }
    public static bool JumpDown() { return Input.GetButtonDown("Jump"); }
    public static bool JumpHeld() { return Input.GetButton("Jump"); }
    public static bool Sprint() { return Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift); }
    public static bool InteractDown() { return Input.GetKeyDown(KeyCode.E); }
    public static bool FireDown() { return Input.GetMouseButtonDown(0); }
    public static bool FireHeld() { return Input.GetMouseButton(0); }
    public static bool PauseDown() { return Input.GetKeyDown(KeyCode.Escape); }
#endif
}

/// <summary>Implemented by anything that moves and can carry riders (moving platforms).</summary>
public interface IMSMover { Vector3 Delta { get; } }

/// <summary>Tiny static event hub so the kits stay independent of each other.</summary>
public static class MSEvents
{
    public static event Action<int> ScoreRequested;
    public static event Action PlayerDied;
    public static readonly HashSet<string> Keys = new HashSet<string>();
    public static Vector3? Checkpoint;
    public static void AddScore(int amount) { if (ScoreRequested != null) ScoreRequested(amount); }
    public static void RaisePlayerDied() { if (PlayerDied != null) PlayerDied(); }
    public static void ResetAll() { Keys.Clear(); Checkpoint = null; }
}
'''

PLAYER_3D = r'''using UnityEngine;

/// <summary>Third/first-person character mover: camera-relative walk, sprint, jump with coyote time, platform carry.</summary>
[RequireComponent(typeof(CharacterController))]
public class MSPlayerController3D : MonoBehaviour
{
    [Header("Movement")]
    public float walkSpeed = 5f;
    public float sprintSpeed = 8f;
    public float jumpHeight = 1.6f;
    public float gravity = -22f;
    public float turnSpeed = 14f;
    [Range(0f, 1f)] public float airControl = 0.6f;
    public float coyoteTime = 0.12f;
    public float jumpBuffer = 0.12f;
    [Header("Camera")]
    public Transform cameraTransform;
    public bool cameraRelative = true;

    public bool IsGrounded { get; private set; }
    public float Speed { get; private set; }
    CharacterController cc;
    Vector3 velocity;
    float coyote, buffer;
    IMSMover platform;

    void Awake()
    {
        cc = GetComponent<CharacterController>();
        if (cameraTransform == null && Camera.main != null) cameraTransform = Camera.main.transform;
    }

    void Update()
    {
        IsGrounded = cc.isGrounded;
        coyote = IsGrounded ? coyoteTime : coyote - Time.deltaTime;
        buffer = MSInput.JumpDown() ? jumpBuffer : buffer - Time.deltaTime;

        Vector2 input = MSInput.Move();
        Vector3 fwd = Vector3.forward, right = Vector3.right;
        if (cameraRelative && cameraTransform != null)
        {
            fwd = Vector3.ProjectOnPlane(cameraTransform.forward, Vector3.up).normalized;
            right = Vector3.ProjectOnPlane(cameraTransform.right, Vector3.up).normalized;
        }
        Vector3 wish = (fwd * input.y + right * input.x);
        float target = MSInput.Sprint() ? sprintSpeed : walkSpeed;
        Vector3 horizontal = new Vector3(velocity.x, 0f, velocity.z);
        float lerp = IsGrounded ? 1f : airControl;
        horizontal = Vector3.Lerp(horizontal, wish * target, 1f - Mathf.Exp(-12f * lerp * Time.deltaTime));
        velocity.x = horizontal.x; velocity.z = horizontal.z;

        if (IsGrounded && velocity.y < 0f) velocity.y = -2f;
        if (buffer > 0f && coyote > 0f)
        {
            velocity.y = Mathf.Sqrt(jumpHeight * -2f * gravity);
            buffer = 0f; coyote = 0f;
        }
        velocity.y += gravity * Time.deltaTime;

        Vector3 move = velocity * Time.deltaTime;
        if (platform != null) move += platform.Delta;
        platform = null;
        cc.Move(move);

        Speed = new Vector3(velocity.x, 0f, velocity.z).magnitude;
        if (wish.sqrMagnitude > 0.01f)
            transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(wish, Vector3.up), 1f - Mathf.Exp(-turnSpeed * Time.deltaTime));
    }

    void OnControllerColliderHit(ControllerColliderHit hit)
    {
        var m = hit.collider.GetComponentInParent<IMSMover>();
        if (m != null && hit.normal.y > 0.5f) platform = m;
    }

    /// <summary>Teleport safely (CharacterController ignores direct transform changes while enabled).</summary>
    public void Teleport(Vector3 position)
    {
        cc.enabled = false; transform.position = position; cc.enabled = true; velocity = Vector3.zero;
    }
}
'''

PLAYER_2D = r'''using UnityEngine;

/// <summary>Side-view platformer mover: run, variable-height jump, coyote time, jump buffer, sprite flip.</summary>
[RequireComponent(typeof(Rigidbody2D), typeof(Collider2D))]
public class MSPlayerController2D : MonoBehaviour
{
    public float moveSpeed = 7f;
    public float acceleration = 60f;
    public float jumpVelocity = 13f;
    public float coyoteTime = 0.1f;
    public float jumpBuffer = 0.1f;
    public LayerMask groundLayers = ~0;
    public bool flipByScale = true;

    public bool IsGrounded { get; private set; }
    Rigidbody2D rb;
    Collider2D col;
    float coyote, buffer;

    Vector2 Vel
    {
#if UNITY_6000_0_OR_NEWER
        get { return rb.linearVelocity; }
        set { rb.linearVelocity = value; }
#else
        get { return rb.velocity; }
        set { rb.velocity = value; }
#endif
    }

    void Awake()
    {
        rb = GetComponent<Rigidbody2D>(); col = GetComponent<Collider2D>();
        rb.freezeRotation = true;
        rb.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
    }

    void Update()
    {
        var b = col.bounds;
        var hits = Physics2D.OverlapBoxAll(new Vector2(b.center.x, b.min.y - 0.04f), new Vector2(b.size.x * 0.9f, 0.08f), 0f, groundLayers);
        IsGrounded = false;
        foreach (var h in hits) if (h != col && !h.isTrigger) { IsGrounded = true; break; }
        coyote = IsGrounded ? coyoteTime : coyote - Time.deltaTime;
        buffer = MSInput.JumpDown() ? jumpBuffer : buffer - Time.deltaTime;
        if (buffer > 0f && coyote > 0f)
        {
            var v = Vel; v.y = jumpVelocity; Vel = v; buffer = 0f; coyote = 0f;
        }
        if (!MSInput.JumpHeld() && Vel.y > 0f) { var v = Vel; v.y *= 1f - 8f * Time.deltaTime; Vel = v; }
        float x = MSInput.Move().x;
        if (flipByScale && Mathf.Abs(x) > 0.05f)
        {
            var s = transform.localScale; s.x = Mathf.Abs(s.x) * Mathf.Sign(x); transform.localScale = s;
        }
    }

    void FixedUpdate()
    {
        var v = Vel;
        v.x = Mathf.MoveTowards(v.x, MSInput.Move().x * moveSpeed, acceleration * Time.fixedDeltaTime);
        Vel = v;
    }
}
'''

THIRD_PERSON_CAMERA = r'''using UnityEngine;

/// <summary>Orbit camera with mouse/stick look, collision pull-in and smoothing. Put it on the Main Camera.</summary>
public class MSThirdPersonCamera : MonoBehaviour
{
    public Transform target;
    public Vector3 pivotOffset = new Vector3(0f, 1.6f, 0f);
    public float distance = 5f;
    public float minPitch = -25f, maxPitch = 70f;
    public float sensitivity = 2.2f;
    public float smoothing = 14f;
    public float collisionRadius = 0.3f;
    public LayerMask obstructionMask = ~0;
    public bool lockCursor = true;

    float yaw, pitch = 15f, currentDistance;

    void Start()
    {
        currentDistance = distance;
        if (target == null) { var p = GameObject.FindWithTag("Player"); if (p != null) target = p.transform; }
        if (target != null) yaw = target.eulerAngles.y;
        SetCursor(lockCursor);
    }

    void SetCursor(bool locked)
    {
        Cursor.lockState = locked ? CursorLockMode.Locked : CursorLockMode.None;
        Cursor.visible = !locked;
    }

    void LateUpdate()
    {
        if (target == null) return;
        if (Time.timeScale > 0f)
        {
            var look = MSInput.Look();
            yaw += look.x * sensitivity;
            pitch = Mathf.Clamp(pitch - look.y * sensitivity, minPitch, maxPitch);
        }
        Quaternion rot = Quaternion.Euler(pitch, yaw, 0f);
        Vector3 pivot = target.position + pivotOffset;
        float want = distance;
        RaycastHit hit;
        if (Physics.SphereCast(pivot, collisionRadius, rot * Vector3.back, out hit, distance, obstructionMask, QueryTriggerInteraction.Ignore) && !hit.transform.IsChildOf(target))
            want = Mathf.Max(0.4f, hit.distance);
        currentDistance = Mathf.Lerp(currentDistance, want, 1f - Mathf.Exp(-smoothing * Time.deltaTime));
        transform.SetPositionAndRotation(pivot + rot * Vector3.back * currentDistance, rot);
    }
}
'''

FOLLOW_CAMERA_2D = r'''using UnityEngine;

/// <summary>Smooth 2D follow camera with look-ahead and optional world limits.</summary>
[RequireComponent(typeof(Camera))]
public class MSFollowCamera2D : MonoBehaviour
{
    public Transform target;
    public float smoothTime = 0.15f;
    public Vector2 offset = new Vector2(0f, 1f);
    public float lookAhead = 1.5f;
    public bool useLimits = false;
    public Vector2 minLimit = new Vector2(-50f, -20f);
    public Vector2 maxLimit = new Vector2(50f, 20f);

    Vector3 vel;
    float lastX, ahead;

    void Start()
    {
        if (target == null) { var p = GameObject.FindWithTag("Player"); if (p != null) target = p.transform; }
        if (target != null) lastX = target.position.x;
    }

    void LateUpdate()
    {
        if (target == null) return;
        float dx = target.position.x - lastX; lastX = target.position.x;
        if (Mathf.Abs(dx) > 0.001f) ahead = Mathf.Lerp(ahead, Mathf.Sign(dx) * lookAhead, 0.1f);
        Vector3 goal = new Vector3(target.position.x + offset.x + ahead, target.position.y + offset.y, transform.position.z);
        if (useLimits) { goal.x = Mathf.Clamp(goal.x, minLimit.x, maxLimit.x); goal.y = Mathf.Clamp(goal.y, minLimit.y, maxLimit.y); }
        transform.position = Vector3.SmoothDamp(transform.position, goal, ref vel, smoothTime);
    }
}
'''

HEALTH = r'''using UnityEngine;
using UnityEngine.Events;

/// <summary>Hit points with damage, healing, regeneration, i-frames and events. Receives SendMessage("TakeDamage", float).</summary>
public class MSHealth : MonoBehaviour
{
    public float maxHealth = 100f;
    public float invulnerableSeconds = 0.25f;
    public float regenPerSecond = 0f;
    public float regenDelay = 4f;
    public bool destroyOnDeath = false;
    public float destroyDelay = 1.5f;
    public bool isPlayer = false;
    public UnityEvent<float> onDamaged;
    public UnityEvent<float> onHealed;
    public UnityEvent onDeath;
    public UnityEvent<float> onHealthChanged;

    public float Current { get; private set; }
    public float Normalized { get { return maxHealth <= 0f ? 0f : Current / maxHealth; } }
    public bool IsDead { get; private set; }
    float lastHit = -999f;

    void Awake() { Current = maxHealth; }

    void Update()
    {
        if (IsDead || regenPerSecond <= 0f || Current >= maxHealth || Time.time - lastHit < regenDelay) return;
        Current = Mathf.Min(maxHealth, Current + regenPerSecond * Time.deltaTime);
        onHealthChanged.Invoke(Current);
    }

    public void TakeDamage(float amount)
    {
        if (IsDead || amount <= 0f || Time.time - lastHit < invulnerableSeconds) return;
        lastHit = Time.time;
        Current = Mathf.Max(0f, Current - amount);
        onDamaged.Invoke(amount);
        onHealthChanged.Invoke(Current);
        if (Current <= 0f) Die();
    }

    public void Heal(float amount)
    {
        if (IsDead || amount <= 0f) return;
        Current = Mathf.Min(maxHealth, Current + amount);
        onHealed.Invoke(amount);
        onHealthChanged.Invoke(Current);
    }

    public void Kill()
    {
        if (IsDead) return;
        Current = 0f;
        onHealthChanged.Invoke(Current);
        Die();
    }

    public void ResetHealth() { IsDead = false; Current = maxHealth; onHealthChanged.Invoke(Current); }

    void Die()
    {
        if (IsDead) return;
        IsDead = true;
        onDeath.Invoke();
        if (isPlayer) MSEvents.RaisePlayerDied();
        if (destroyOnDeath) Destroy(gameObject, destroyDelay);
    }
}
'''

COLLECTIBLE = r'''using UnityEngine;
using UnityEngine.Events;

/// <summary>Pickup (coin, gem, key, heal). Needs a trigger Collider. Spins and bobs; reports score and key ids through MSEvents.</summary>
public class MSCollectible : MonoBehaviour
{
    public int score = 10;
    public float healAmount = 0f;
    public string keyId = "";
    public string requiredTag = "Player";
    public float spinDegreesPerSecond = 120f;
    public float bobHeight = 0.15f;
    public float bobSpeed = 2f;
    public GameObject pickupEffect;
    public AudioClip pickupSound;
    public UnityEvent onCollected;

    Vector3 start;
    bool taken;

    void Reset() { var c = GetComponent<Collider>(); if (c != null) c.isTrigger = true; var c2 = GetComponent<Collider2D>(); if (c2 != null) c2.isTrigger = true; }
    void Start() { start = transform.position; }

    void Update()
    {
        transform.Rotate(0f, spinDegreesPerSecond * Time.deltaTime, 0f, Space.World);
        transform.position = start + Vector3.up * (Mathf.Sin(Time.time * bobSpeed) * bobHeight);
    }

    void OnTriggerEnter(Collider other) { Collect(other.gameObject); }
    void OnTriggerEnter2D(Collider2D other) { Collect(other.gameObject); }

    void Collect(GameObject who)
    {
        if (taken) return;
        if (!string.IsNullOrEmpty(requiredTag) && !who.CompareTag(requiredTag) && (who.transform.root == null || !who.transform.root.CompareTag(requiredTag))) return;
        taken = true;
        if (score != 0) MSEvents.AddScore(score);
        if (!string.IsNullOrEmpty(keyId)) MSEvents.Keys.Add(keyId);
        if (healAmount > 0f) who.SendMessageUpwards("Heal", healAmount, SendMessageOptions.DontRequireReceiver);
        if (pickupEffect != null) Instantiate(pickupEffect, transform.position, Quaternion.identity);
        if (pickupSound != null) AudioSource.PlayClipAtPoint(pickupSound, transform.position);
        onCollected.Invoke();
        Destroy(gameObject);
    }
}
'''

CHECKPOINT = r'''using UnityEngine;

/// <summary>Checkpoint trigger. Entering it stores the respawn point used by MSRespawn.</summary>
public class MSCheckpoint : MonoBehaviour
{
    public string requiredTag = "Player";
    public Color activeColor = new Color(0.3f, 1f, 0.5f, 1f);
    public bool activated;

    void Reset() { var c = GetComponent<Collider>(); if (c != null) c.isTrigger = true; }

    void OnTriggerEnter(Collider other)
    {
        if (!other.CompareTag(requiredTag) && !other.transform.root.CompareTag(requiredTag)) return;
        MSEvents.Checkpoint = transform.position + Vector3.up * 0.5f;
        if (!activated)
        {
            activated = true;
            var r = GetComponentInChildren<Renderer>();
            if (r != null) r.material.color = activeColor;
        }
    }
}
'''

RESPAWN = r'''using UnityEngine;

/// <summary>Put on the player. Respawn() returns it to the last MSCheckpoint (or where it started) and resets health.</summary>
public class MSRespawn : MonoBehaviour
{
    public float fallY = -50f;
    public float respawnDelay = 0.6f;
    Vector3 startPos;
    bool pending;

    void Start() { startPos = transform.position; }
    void Update() { if (transform.position.y < fallY) Respawn(); }

    public void Respawn() { if (!pending) StartCoroutine(Do()); }

    System.Collections.IEnumerator Do()
    {
        pending = true;
        yield return new WaitForSeconds(respawnDelay);
        Vector3 p = MSEvents.Checkpoint.HasValue ? MSEvents.Checkpoint.Value : startPos;
        var cc = GetComponent<CharacterController>();
        if (cc != null) cc.enabled = false;
        transform.position = p;
        if (cc != null) cc.enabled = true;
        var rb = GetComponent<Rigidbody>();
        if (rb != null)
        {
#if UNITY_6000_0_OR_NEWER
            rb.linearVelocity = Vector3.zero;
#else
            rb.velocity = Vector3.zero;
#endif
            rb.angularVelocity = Vector3.zero;
        }
        var rb2 = GetComponent<Rigidbody2D>();
        if (rb2 != null)
        {
#if UNITY_6000_0_OR_NEWER
            rb2.linearVelocity = Vector2.zero;
#else
            rb2.velocity = Vector2.zero;
#endif
            rb2.angularVelocity = 0f;
        }
        var h = GetComponent<MSHealth>(); if (h != null) h.ResetHealth();
        pending = false;
    }
}
'''

KILL_ZONE = r'''using UnityEngine;

/// <summary>Trigger volume that kills or respawns whatever enters it (lava, pits, spikes).</summary>
public class MSKillZone : MonoBehaviour
{
    public float damage = 0f; // 0 = instant kill / respawn
    public string requiredTag = "";

    void Reset() { var c = GetComponent<Collider>(); if (c != null) c.isTrigger = true; var c2 = GetComponent<Collider2D>(); if (c2 != null) c2.isTrigger = true; }
    void OnTriggerEnter(Collider other) { Hit(other.gameObject); }
    void OnTriggerEnter2D(Collider2D other) { Hit(other.gameObject); }

    void Hit(GameObject g)
    {
        if (!string.IsNullOrEmpty(requiredTag) && !g.CompareTag(requiredTag) && !g.transform.root.CompareTag(requiredTag)) return;
        if (damage > 0f) { g.SendMessageUpwards("TakeDamage", damage, SendMessageOptions.DontRequireReceiver); return; }
        g.SendMessageUpwards("Respawn", SendMessageOptions.DontRequireReceiver);
        g.SendMessageUpwards("Kill", SendMessageOptions.DontRequireReceiver);
    }
}
'''

MOVING_PLATFORM = r'''using UnityEngine;

/// <summary>Kinematic platform that travels between waypoints (or A to B by offset). Carries CharacterController, Rigidbody and 2D riders.</summary>
public class MSMovingPlatform : MonoBehaviour, IMSMover
{
    public Transform[] waypoints;
    public Vector3 localOffset = new Vector3(0f, 0f, 6f);
    public float speed = 2f;
    public float waitSeconds = 0.5f;
    public bool pingPong = true;

    public Vector3 Delta { get; private set; }
    Vector3 a, b;
    int idx, dir = 1;
    float waitUntil;
    Rigidbody rb;

    void Start()
    {
        a = transform.position;
        b = transform.TransformPoint(localOffset);
        rb = GetComponent<Rigidbody>();
        if (rb != null) rb.isKinematic = true;
    }

    Vector3 Goal()
    {
        if (waypoints != null && waypoints.Length > 0) return waypoints[Mathf.Clamp(idx, 0, waypoints.Length - 1)].position;
        return idx == 0 ? a : b;
    }

    void FixedUpdate()
    {
        Delta = Vector3.zero;
        if (Time.time < waitUntil) return;
        Vector3 goal = Goal();
        Vector3 next = Vector3.MoveTowards(transform.position, goal, speed * Time.fixedDeltaTime);
        Delta = next - transform.position;
        if (rb != null) rb.MovePosition(next); else transform.position = next;
        if ((next - goal).sqrMagnitude < 0.0004f)
        {
            int count = (waypoints != null && waypoints.Length > 0) ? waypoints.Length : 2;
            if (pingPong) { if (idx + dir >= count || idx + dir < 0) dir = -dir; idx += dir; }
            else idx = (idx + 1) % count;
            waitUntil = Time.time + waitSeconds;
        }
    }

    void OnCollisionEnter(Collision c) { if (c.rigidbody != null && c.contacts.Length > 0 && c.contacts[0].normal.y < -0.5f) c.transform.SetParent(transform, true); }
    void OnCollisionExit(Collision c) { if (c.transform.parent == transform) c.transform.SetParent(null, true); }
    void OnCollisionEnter2D(Collision2D c) { if (c.rigidbody != null && c.contacts.Length > 0 && c.contacts[0].normal.y < -0.5f) c.transform.SetParent(transform, true); }
    void OnCollisionExit2D(Collision2D c) { if (c.transform.parent == transform) c.transform.SetParent(null, true); }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.cyan;
        if (waypoints != null && waypoints.Length > 0) { foreach (var w in waypoints) if (w != null) Gizmos.DrawWireSphere(w.position, 0.3f); }
        else Gizmos.DrawLine(transform.position, transform.TransformPoint(localOffset));
    }
}
'''

PROJECTILE = r'''using UnityEngine;

/// <summary>Bullet/fireball: flies forward, damages whatever it hits via SendMessage("TakeDamage"), then disappears.</summary>
public class MSProjectile : MonoBehaviour
{
    public float speed = 30f;
    public float damage = 10f;
    public float lifetime = 4f;
    public float radius = 0.1f;
    public LayerMask hitMask = ~0;
    public GameObject impactEffect;
    [HideInInspector] public GameObject owner;

    void Start() { Destroy(gameObject, lifetime); }

    void Update()
    {
        float step = speed * Time.deltaTime;
        RaycastHit hit;
        if (Physics.SphereCast(transform.position, radius, transform.forward, out hit, step, hitMask, QueryTriggerInteraction.Ignore))
        {
            if (owner == null || !hit.transform.IsChildOf(owner.transform)) { Impact(hit); return; }
        }
        transform.position += transform.forward * step;
    }

    void Impact(RaycastHit hit)
    {
        hit.collider.SendMessageUpwards("TakeDamage", damage, SendMessageOptions.DontRequireReceiver);
        if (hit.rigidbody != null) hit.rigidbody.AddForceAtPosition(transform.forward * damage, hit.point, ForceMode.Impulse);
        if (impactEffect != null) Instantiate(impactEffect, hit.point, Quaternion.LookRotation(hit.normal));
        Destroy(gameObject);
    }
}
'''

SHOOTER = r'''using UnityEngine;

/// <summary>Fires MSProjectile (or a generated glowing sphere) from a muzzle toward the camera crosshair.</summary>
public class MSShooter : MonoBehaviour
{
    public MSProjectile projectilePrefab;
    public Transform muzzle;
    public float fireRate = 6f;
    public bool automatic = true;
    public bool aimWithCamera = true;
    public float damage = 10f;
    public float speed = 40f;
    public float spreadDegrees = 0.5f;
    public int ammo = -1; // -1 = infinite
    float next;

    void Update()
    {
        bool fire = automatic ? MSInput.FireHeld() : MSInput.FireDown();
        if (fire && Time.time >= next && ammo != 0) { next = Time.time + 1f / Mathf.Max(0.1f, fireRate); Shoot(); }
    }

    public void Shoot()
    {
        Transform m = muzzle != null ? muzzle : transform;
        Vector3 dir = m.forward;
        if (aimWithCamera && Camera.main != null)
        {
            Ray r = Camera.main.ViewportPointToRay(new Vector3(0.5f, 0.5f, 0f));
            Vector3 aim = Physics.Raycast(r, out RaycastHit h, 500f, ~0, QueryTriggerInteraction.Ignore) ? h.point : r.GetPoint(500f);
            dir = (aim - m.position).normalized;
        }
        dir = Quaternion.Euler(Random.Range(-spreadDegrees, spreadDegrees), Random.Range(-spreadDegrees, spreadDegrees), 0f) * dir;
        MSProjectile p;
        if (projectilePrefab != null) p = Instantiate(projectilePrefab, m.position, Quaternion.LookRotation(dir));
        else
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            g.transform.localScale = Vector3.one * 0.25f; g.transform.SetPositionAndRotation(m.position, Quaternion.LookRotation(dir));
            Destroy(g.GetComponent<Collider>());
            p = g.AddComponent<MSProjectile>();
        }
        p.damage = damage; p.speed = speed; p.owner = gameObject;
        if (ammo > 0) ammo--;
    }
}
'''

ENEMY_AI = r'''using UnityEngine;
using UnityEngine.AI;

/// <summary>Patrol / chase / attack enemy. Uses a NavMeshAgent when present (bake a NavMesh), otherwise walks in a straight line.</summary>
public class MSEnemyAI : MonoBehaviour
{
    public enum State { Patrol, Chase, Attack, Return }
    public Transform[] patrolPoints;
    public float walkSpeed = 2f;
    public float chaseSpeed = 4.5f;
    public float sightRange = 12f;
    [Range(10f, 360f)] public float sightAngle = 140f;
    public float attackRange = 1.8f;
    public float attackDamage = 10f;
    public float attackCooldown = 1.2f;
    public float loseSightSeconds = 3f;
    public string targetTag = "Player";
    public State state = State.Patrol;

    Transform target;
    NavMeshAgent agent;
    Vector3 home;
    int pIdx;
    float lastSeen = -99f, nextAttack, wait;

    void Start()
    {
        home = transform.position;
        agent = GetComponent<NavMeshAgent>();
        var p = GameObject.FindWithTag(targetTag);
        if (p != null) target = p.transform;
    }

    bool CanSee()
    {
        if (target == null) return false;
        Vector3 to = target.position - transform.position;
        if (to.magnitude > sightRange) return false;
        if (Vector3.Angle(transform.forward, to) > sightAngle * 0.5f && to.magnitude > attackRange) return false;
        RaycastHit hit;
        if (Physics.Raycast(transform.position + Vector3.up, (target.position + Vector3.up - transform.position - Vector3.up).normalized, out hit, sightRange, ~0, QueryTriggerInteraction.Ignore))
            return hit.transform == target || hit.transform.IsChildOf(target);
        return true;
    }

    void Go(Vector3 pos, float speed)
    {
        if (agent != null && agent.isOnNavMesh) { agent.speed = speed; agent.SetDestination(pos); return; }
        Vector3 flat = new Vector3(pos.x, transform.position.y, pos.z);
        transform.position = Vector3.MoveTowards(transform.position, flat, speed * Time.deltaTime);
        Vector3 d = flat - transform.position;
        if (d.sqrMagnitude > 0.001f) transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(d), 8f * Time.deltaTime);
    }

    void Update()
    {
        bool sees = CanSee();
        if (sees) lastSeen = Time.time;
        float dist = target != null ? Vector3.Distance(transform.position, target.position) : 999f;
        switch (state)
        {
            case State.Patrol:
                if (sees) { state = State.Chase; break; }
                if (patrolPoints != null && patrolPoints.Length > 0)
                {
                    Vector3 g = patrolPoints[pIdx].position;
                    Go(g, walkSpeed);
                    if ((new Vector3(g.x, transform.position.y, g.z) - transform.position).sqrMagnitude < 0.6f)
                    { wait += Time.deltaTime; if (wait > 1f) { wait = 0f; pIdx = (pIdx + 1) % patrolPoints.Length; } }
                }
                break;
            case State.Chase:
                if (!sees && Time.time - lastSeen > loseSightSeconds) { state = State.Return; break; }
                if (dist <= attackRange) { state = State.Attack; break; }
                Go(target.position, chaseSpeed);
                break;
            case State.Attack:
                if (dist > attackRange * 1.3f) { state = State.Chase; break; }
                if (agent != null && agent.isOnNavMesh) agent.ResetPath();
                if (Time.time >= nextAttack)
                {
                    nextAttack = Time.time + attackCooldown;
                    target.SendMessageUpwards("TakeDamage", attackDamage, SendMessageOptions.DontRequireReceiver);
                }
                break;
            case State.Return:
                if (sees) { state = State.Chase; break; }
                Go(home, walkSpeed);
                if ((new Vector3(home.x, transform.position.y, home.z) - transform.position).sqrMagnitude < 0.5f) state = State.Patrol;
                break;
        }
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow; Gizmos.DrawWireSphere(transform.position, sightRange);
        Gizmos.color = Color.red; Gizmos.DrawWireSphere(transform.position, attackRange);
    }
}
'''

SPAWNER = r'''using System.Collections;
using System.Collections.Generic;
using UnityEngine;

/// <summary>Spawns prefabs on a timer or in waves inside a circle, capped by maxAlive.</summary>
public class MSSpawner : MonoBehaviour
{
    public GameObject prefab;
    public float interval = 3f;
    public int maxAlive = 8;
    public int totalLimit = 0; // 0 = endless
    public float radius = 6f;
    public bool snapToGround = true;
    public bool startOnAwake = true;
    public int waveSize = 1;

    readonly List<GameObject> alive = new List<GameObject>();
    int spawned;

    void Start() { if (startOnAwake) StartCoroutine(Loop()); }
    public void Begin() { StopAllCoroutines(); StartCoroutine(Loop()); }

    IEnumerator Loop()
    {
        while (totalLimit == 0 || spawned < totalLimit)
        {
            alive.RemoveAll(g => g == null);
            for (int i = 0; i < waveSize && alive.Count < maxAlive && (totalLimit == 0 || spawned < totalLimit); i++) Spawn();
            yield return new WaitForSeconds(interval);
        }
    }

    public GameObject Spawn()
    {
        if (prefab == null) return null;
        Vector2 c = Random.insideUnitCircle * radius;
        Vector3 pos = transform.position + new Vector3(c.x, 0f, c.y);
        RaycastHit hit;
        if (snapToGround && Physics.Raycast(pos + Vector3.up * 50f, Vector3.down, out hit, 200f, ~0, QueryTriggerInteraction.Ignore)) pos = hit.point;
        var g = Instantiate(prefab, pos, Quaternion.Euler(0f, Random.value * 360f, 0f));
        alive.Add(g); spawned++;
        return g;
    }

    void OnDrawGizmosSelected() { Gizmos.color = Color.green; Gizmos.DrawWireSphere(transform.position, radius); }
}
'''

GAME_MANAGER = r'''using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;

/// <summary>Singleton game state: score, lives, timer, win/lose. Listens to MSEvents (collectibles add score, MSHealth player death costs a life).</summary>
public class MSGameManager : MonoBehaviour
{
    public enum GameState { Playing, Paused, GameOver, Won }
    public static MSGameManager Instance { get; private set; }

    public int startingLives = 3;
    public int scoreToWin = 0; // 0 = no score win condition
    public float timeLimit = 0f; // seconds, 0 = none
    public UnityEvent<int> onScoreChanged;
    public UnityEvent<int> onLivesChanged;
    public UnityEvent<float> onTimeChanged;
    public UnityEvent onGameOver;
    public UnityEvent onWin;

    public int Score { get; private set; }
    public int Lives { get; private set; }
    public float TimeLeft { get; private set; }
    public GameState State { get; private set; }

    void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        Lives = startingLives; TimeLeft = timeLimit; State = GameState.Playing;
        Time.timeScale = 1f;
    }

    void OnEnable() { MSEvents.ScoreRequested += AddScore; MSEvents.PlayerDied += LoseLife; }
    void OnDisable() { MSEvents.ScoreRequested -= AddScore; MSEvents.PlayerDied -= LoseLife; }

    void Update()
    {
        if (State != GameState.Playing || timeLimit <= 0f) return;
        TimeLeft = Mathf.Max(0f, TimeLeft - Time.deltaTime);
        onTimeChanged.Invoke(TimeLeft);
        if (TimeLeft <= 0f) GameOver();
    }

    public void AddScore(int amount)
    {
        if (State != GameState.Playing) return;
        Score += amount; onScoreChanged.Invoke(Score);
        if (scoreToWin > 0 && Score >= scoreToWin) Win();
    }

    public void LoseLife()
    {
        if (State != GameState.Playing) return;
        Lives--; onLivesChanged.Invoke(Lives);
        if (Lives <= 0) GameOver();
    }

    public void GameOver() { if (State != GameState.Playing) return; State = GameState.GameOver; onGameOver.Invoke(); }
    public void Win() { if (State != GameState.Playing) return; State = GameState.Won; onWin.Invoke(); }
    public void Restart() { MSEvents.ResetAll(); Time.timeScale = 1f; SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex); }
    public void LoadScene(string sceneName) { Time.timeScale = 1f; SceneManager.LoadScene(sceneName); }
    public void Quit() { Application.Quit(); }
}
'''

SAVE_SYSTEM = r'''using System;
using System.IO;
using UnityEngine;

/// <summary>JSON save slots in Application.persistentDataPath. Use MSSave.Save/Load for your own [Serializable] classes.</summary>
public static class MSSave
{
    static string PathFor(string slot) { return Path.Combine(Application.persistentDataPath, "save_" + slot + ".json"); }
    public static bool Exists(string slot) { return File.Exists(PathFor(slot)); }
    public static void Save<T>(string slot, T data) { File.WriteAllText(PathFor(slot), JsonUtility.ToJson(data, true)); }
    public static T Load<T>(string slot, T fallback = default(T))
    {
        try { return Exists(slot) ? JsonUtility.FromJson<T>(File.ReadAllText(PathFor(slot))) : fallback; }
        catch (Exception e) { Debug.LogWarning("MSSave: could not read slot " + slot + ": " + e.Message); return fallback; }
    }
    public static void Delete(string slot) { if (Exists(slot)) File.Delete(PathFor(slot)); }
}

[Serializable]
public class MSSaveData
{
    public Vector3 playerPosition;
    public string[] keys;
    public string savedAt;
}

/// <summary>Quick save/load of the player position, score and keys. F5 saves, F9 loads; autosaves on quit.</summary>
public class MSSaveSystem : MonoBehaviour
{
    public string slot = "slot1";
    public Transform player;
    public bool autoSaveOnQuit = true;
    public bool loadOnStart = false;

    void Start()
    {
        if (player == null) { var p = GameObject.FindWithTag("Player"); if (p != null) player = p.transform; }
        if (loadOnStart) Load();
    }

    void Update()
    {
#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER
        var kb = UnityEngine.InputSystem.Keyboard.current;
        if (kb != null && kb.f5Key.wasPressedThisFrame) Save();
        if (kb != null && kb.f9Key.wasPressedThisFrame) Load();
#else
        if (Input.GetKeyDown(KeyCode.F5)) Save();
        if (Input.GetKeyDown(KeyCode.F9)) Load();
#endif
    }

    public void Save()
    {
        var d = new MSSaveData { savedAt = DateTime.Now.ToString("s") };
        if (player != null) d.playerPosition = player.position;
        var keys = new string[MSEvents.Keys.Count]; MSEvents.Keys.CopyTo(keys); d.keys = keys;
        MSSave.Save(slot, d);
        Debug.Log("MSSaveSystem: saved to " + Application.persistentDataPath);
    }

    public void Load()
    {
        if (!MSSave.Exists(slot)) return;
        var d = MSSave.Load<MSSaveData>(slot);
        if (d == null) return;
        if (player != null)
        {
            var cc = player.GetComponent<CharacterController>();
            if (cc != null) cc.enabled = false;
            player.position = d.playerPosition;
            if (cc != null) cc.enabled = true;
        }
        MSEvents.Keys.Clear();
        if (d.keys != null) foreach (var k in d.keys) MSEvents.Keys.Add(k);
    }

    void OnApplicationQuit() { if (autoSaveOnQuit) Save(); }
}
'''

PAUSE_MENU = r'''using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

/// <summary>Pause toggle (Esc / Start). Assign the panel from ms_unity_ui_kit(pause); buttons named Btn_Resume / Btn_Restart / Btn_Quit are wired automatically.</summary>
public class MSPauseMenu : MonoBehaviour
{
    public GameObject panel;
    public bool unlockCursor = true;
    public bool IsPaused { get; private set; }

    void Awake()
    {
        if (panel == null) return;
        foreach (var b in panel.GetComponentsInChildren<Button>(true))
        {
            string n = b.name.ToLowerInvariant();
            if (n.Contains("resume")) b.onClick.AddListener(Resume);
            else if (n.Contains("restart")) b.onClick.AddListener(Restart);
            else if (n.Contains("quit")) b.onClick.AddListener(Quit);
        }
        panel.SetActive(false);
    }

    void Update() { if (MSInput.PauseDown()) { if (IsPaused) Resume(); else Pause(); } }

    public void Pause()
    {
        IsPaused = true; Time.timeScale = 0f; AudioListener.pause = true;
        if (panel != null) panel.SetActive(true);
        if (unlockCursor) { Cursor.lockState = CursorLockMode.None; Cursor.visible = true; }
    }

    public void Resume()
    {
        IsPaused = false; Time.timeScale = 1f; AudioListener.pause = false;
        if (panel != null) panel.SetActive(false);
        if (unlockCursor) { Cursor.lockState = CursorLockMode.Locked; Cursor.visible = false; }
    }

    public void Restart() { Resume(); MSEvents.ResetAll(); SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex); }
    public void Quit()
    {
#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }
}
'''

CAMERA_SHAKE = r'''using UnityEngine;

/// <summary>Trauma-based camera shake. Put on the camera (or its parent) and call MSCameraShake.Shake(0.5f) from anywhere.</summary>
public class MSCameraShake : MonoBehaviour
{
    public static MSCameraShake Instance;
    public float maxOffset = 0.35f;
    public float maxRollDegrees = 3f;
    public float decay = 1.6f;
    public float frequency = 22f;
    float trauma;
    Vector3 basePos; Quaternion baseRot;
    bool applied;

    void Awake() { Instance = this; }

    public static void Shake(float amount = 0.5f)
    {
        if (Instance == null && Camera.main != null) Instance = Camera.main.gameObject.AddComponent<MSCameraShake>();
        if (Instance != null) Instance.trauma = Mathf.Clamp01(Instance.trauma + amount);
    }

    void LateUpdate()
    {
        if (applied) { transform.localPosition = basePos; transform.localRotation = baseRot; applied = false; }
        if (trauma <= 0f) return;
        basePos = transform.localPosition; baseRot = transform.localRotation; applied = true;
        float s = trauma * trauma, t = Time.time * frequency;
        Vector3 off = new Vector3(Mathf.PerlinNoise(t, 0f) - 0.5f, Mathf.PerlinNoise(0f, t) - 0.5f, 0f) * 2f * maxOffset * s;
        float roll = (Mathf.PerlinNoise(t, t) - 0.5f) * 2f * maxRollDegrees * s;
        transform.localPosition = basePos + off;
        transform.localRotation = baseRot * Quaternion.Euler(0f, 0f, roll);
        trauma = Mathf.Max(0f, trauma - decay * Time.deltaTime);
    }
}
'''

INTERACTABLE = r'''using UnityEngine;
using UnityEngine.Events;

/// <summary>Press E (or gamepad West) near the object to trigger onInteract. Optional prompt object is shown while in range. Needs a trigger Collider.</summary>
public class MSInteractable : MonoBehaviour
{
    public string requiredTag = "Player";
    public string requiredKeyId = "";
    public bool once = false;
    public GameObject prompt;
    public UnityEvent onInteract;
    public UnityEvent onLocked;

    bool inRange, used;

    void Reset() { var c = GetComponent<Collider>(); if (c != null) c.isTrigger = true; }
    void Start() { if (prompt != null) prompt.SetActive(false); }

    void OnTriggerEnter(Collider o) { if (Match(o.gameObject)) { inRange = true; if (prompt != null && !used) prompt.SetActive(true); } }
    void OnTriggerExit(Collider o) { if (Match(o.gameObject)) { inRange = false; if (prompt != null) prompt.SetActive(false); } }
    bool Match(GameObject g) { return string.IsNullOrEmpty(requiredTag) || g.CompareTag(requiredTag) || g.transform.root.CompareTag(requiredTag); }

    void Update()
    {
        if (!inRange || (once && used) || !MSInput.InteractDown()) return;
        if (!string.IsNullOrEmpty(requiredKeyId) && !MSEvents.Keys.Contains(requiredKeyId)) { onLocked.Invoke(); return; }
        used = true;
        onInteract.Invoke();
        if (once && prompt != null) prompt.SetActive(false);
    }
}
'''

DOOR = r'''using UnityEngine;

/// <summary>Door/gate that swings or slides open when the player enters its trigger (or on Toggle()). Can require a key id from MSCollectible.</summary>
public class MSDoor : MonoBehaviour
{
    public enum Mode { Swing, SlideUp, SlideSide }
    public Mode mode = Mode.Swing;
    public Transform door;
    public float openAmount = 90f; // degrees for Swing, metres for slides
    public float speed = 3f;
    public string requiredKeyId = "";
    public bool autoOpen = true;
    public bool autoClose = true;
    public string requiredTag = "Player";
    public bool IsOpen { get; private set; }

    Vector3 closedPos; Quaternion closedRot;
    float t;

    void Reset() { var c = GetComponent<Collider>(); if (c != null) c.isTrigger = true; }

    void Start()
    {
        if (door == null) door = transform;
        closedPos = door.localPosition; closedRot = door.localRotation;
    }

    bool Allowed() { return string.IsNullOrEmpty(requiredKeyId) || MSEvents.Keys.Contains(requiredKeyId); }
    public void Open() { if (Allowed()) IsOpen = true; }
    public void Close() { IsOpen = false; }
    public void Toggle() { if (IsOpen) Close(); else Open(); }

    void OnTriggerEnter(Collider o) { if (autoOpen && Match(o.gameObject)) Open(); }
    void OnTriggerExit(Collider o) { if (autoClose && Match(o.gameObject)) Close(); }
    bool Match(GameObject g) { return string.IsNullOrEmpty(requiredTag) || g.CompareTag(requiredTag) || g.transform.root.CompareTag(requiredTag); }

    void Update()
    {
        t = Mathf.MoveTowards(t, IsOpen ? 1f : 0f, speed * Time.deltaTime);
        float e = Mathf.SmoothStep(0f, 1f, t);
        switch (mode)
        {
            case Mode.Swing: door.localRotation = closedRot * Quaternion.Euler(0f, openAmount * e, 0f); break;
            case Mode.SlideUp: door.localPosition = closedPos + Vector3.up * (openAmount * e); break;
            default: door.localPosition = closedPos + Vector3.right * (openAmount * e); break;
        }
    }
}
'''

# kind -> (files {class: code}, summary, attach {component: default target hint}, setup notes)
KINDS = {
    "player_controller_3d": ({"MSPlayerController3D": PLAYER_3D}, "CharacterController mover (camera-relative, sprint, coyote jump, platform carry)", "MSPlayerController3D", "Tag the object Player; pair with third_person_camera."),
    "player_controller_2d": ({"MSPlayerController2D": PLAYER_2D}, "Rigidbody2D platformer mover (coyote time, jump buffer, variable jump)", "MSPlayerController2D", "Needs a Collider2D; put ground on a physics layer or leave groundLayers = Everything."),
    "third_person_camera": ({"MSThirdPersonCamera": THIRD_PERSON_CAMERA}, "Orbit camera with look input and collision pull-in", "MSThirdPersonCamera", "Add to the Main Camera; assign target or tag your player Player."),
    "follow_camera_2d": ({"MSFollowCamera2D": FOLLOW_CAMERA_2D}, "Smooth 2D follow camera with look-ahead and limits", "MSFollowCamera2D", "Add to the Main Camera."),
    "health": ({"MSHealth": HEALTH}, "Hit points, damage/heal events, regen, i-frames, death", "MSHealth", "Other scripts call SendMessage('TakeDamage', amount)."),
    "collectible": ({"MSCollectible": COLLECTIBLE}, "Spinning pickup: score, heal, key id, effect, sound", "MSCollectible", "Needs a trigger collider (set automatically by Reset)."),
    "checkpoint_respawn": ({"MSCheckpoint": CHECKPOINT, "MSRespawn": RESPAWN}, "Checkpoint triggers + player respawn (fall limit, health reset)", "MSCheckpoint", "Add MSRespawn to the player and MSCheckpoint to trigger volumes."),
    "kill_zone": ({"MSKillZone": KILL_ZONE}, "Trigger that kills/damages/respawns (lava, pits, spikes)", "MSKillZone", "Pair with checkpoint_respawn for respawning."),
    "moving_platform": ({"MSMovingPlatform": MOVING_PLATFORM}, "Waypoint or A-B platform that carries riders", "MSMovingPlatform", "Works with player_controller_3d; Rigidbody riders are parented."),
    "shooter": ({"MSProjectile": PROJECTILE, "MSShooter": SHOOTER}, "Camera-aimed shooter + damaging projectile", "MSShooter", "Put MSShooter on the player or weapon; targets need MSHealth."),
    "enemy_patrol_chase": ({"MSEnemyAI": ENEMY_AI}, "Patrol, sight cone, chase, melee attack (NavMeshAgent optional)", "MSEnemyAI", "Bake a NavMesh with ms_unity_navmesh for pathfinding around walls."),
    "spawner": ({"MSSpawner": SPAWNER}, "Timed/wave prefab spawner with alive cap and ground snap", "MSSpawner", "Assign the prefab."),
    "game_manager": ({"MSGameManager": GAME_MANAGER}, "Score, lives, timer, win/lose events (singleton)", "MSGameManager", "One per scene; hook UnityEvents to UI."),
    "save_system": ({"MSSaveSystem": SAVE_SYSTEM}, "JSON save slots + quick save (F5) / load (F9) of player position and keys", "MSSaveSystem", "Use MSSave.Save<T>/Load<T> for your own data classes."),
    "pause_menu": ({"MSPauseMenu": PAUSE_MENU}, "Pause toggle that wires Btn_Resume/Restart/Quit of a uGUI panel", "MSPauseMenu", "Build the panel with ms_unity_ui_kit screen=pause and assign it."),
    "camera_shake": ({"MSCameraShake": CAMERA_SHAKE}, "Trauma-based screen shake: MSCameraShake.Shake(0.5f)", "MSCameraShake", "Add to the camera."),
    "interactable": ({"MSInteractable": INTERACTABLE}, "Press E in range -> UnityEvent, optional key requirement and prompt", "MSInteractable", "Needs a trigger collider."),
    "door": ({"MSDoor": DOOR}, "Swing/slide door with key requirement and auto open/close", "MSDoor", "Assign `door` to the moving part; trigger collider on this object."),
}
