; md5.asm - Table-driven MD5 compression function (x64)
; Matches RFC 1321

section .data
align 4

K_BASE:
    dd 0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee
    dd 0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501
    dd 0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be
    dd 0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821
    dd 0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa
    dd 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8
    dd 0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed
    dd 0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a
    dd 0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c
    dd 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70
    dd 0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05
    dd 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665
    dd 0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039
    dd 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1
    dd 0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1
    dd 0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391

S_BASE:
    db 7, 12, 17, 22
    db 7, 12, 17, 22
    db 7, 12, 17, 22
    db 7, 12, 17, 22
    db 5, 9, 14, 20
    db 5, 9, 14, 20
    db 5, 9, 14, 20
    db 5, 9, 14, 20
    db 4, 11, 16, 23
    db 4, 11, 16, 23
    db 4, 11, 16, 23
    db 4, 11, 16, 23
    db 6, 10, 15, 21
    db 6, 10, 15, 21
    db 6, 10, 15, 21
    db 6, 10, 15, 21

section .text
global MD5_Compress

MD5_Compress:
    push rbp
    mov rbp, rsp
    push rbx
    push rdi
    push rsi
    push r12
    push r13
    push r14
    push r15
    
    mov rdi, rcx    ; State
    mov rsi, rdx    ; Block

    mov r8d, [rdi]      ; A
    mov r9d, [rdi+4]    ; B
    mov r10d, [rdi+8]   ; C
    mov r11d, [rdi+12]  ; D
    
    xor r12, r12 ; i = 0

.loop:
    cmp r12, 16
    jl .round1
    cmp r12, 32
    jl .round2
    cmp r12, 48
    jl .round3
    jmp .round4

.round1:
    mov eax, r10d
    xor eax, r11d
    and eax, r9d
    xor eax, r11d   ; F
    mov r13, r12    ; g
    jmp .calc

.round2:
    mov eax, r11d
    not eax
    and eax, r10d
    mov ebx, r11d
    and ebx, r9d
    or eax, ebx     ; G
    mov r13, r12
    imul r13, 5
    inc r13
    and r13, 15     ; g
    jmp .calc

.round3:
    mov eax, r9d
    xor eax, r10d
    xor eax, r11d   ; H
    mov r13, r12
    imul r13, 3
    add r13, 5
    and r13, 15     ; g
    jmp .calc

.round4:
    mov eax, r11d
    not eax
    or eax, r9d
    xor eax, r10d   ; I
    mov r13, r12
    imul r13, 7
    and r13, 15     ; g
    jmp .calc

.calc:
    add r8d, eax
    
    ; Address calculation manual to avoid complex modes
    lea r14, [rel K_BASE]
    mov eax, r12d
    mov eax, [r14 + rax*4] ; Load K[i]
    add r8d, eax
    
    mov eax, r13d
    add r8d, [rsi + rax*4] ; Load block[g]
    
    lea r14, [rel S_BASE]
    mov rcx, r12
    mov cl, [r14 + rcx]    ; Load S[i]
    rol r8d, cl
    
    add r8d, r9d
    
    ; Rotate vars
    mov eax, r11d
    mov r11d, r10d
    mov r10d, r9d
    mov r9d, r8d
    mov r8d, eax
    
    inc r12
    cmp r12, 64
    jl .loop

    add [rdi], r8d
    add [rdi+4], r9d
    add [rdi+8], r10d
    add [rdi+12], r11d

    pop r15
    pop r14
    pop r13
    pop r12
    pop rsi
    pop rdi
    pop rbx
    pop rbp
    ret