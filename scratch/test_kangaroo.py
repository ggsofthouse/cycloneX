import coincurve, sys

target_hex = "030d282cf2ff536d2c42f105d0b8588821a915dc3f9a05bd98bb23af67a2e92a5b"
target_pk = coincurve.PublicKey(bytes.fromhex(target_hex))
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

range_start = 0x20000000
range_end = 0x3fffffff

# Jump table: 32 jump sizes centered around 2^14 (mean jump size for 30-bit)
jump_sizes = [(1 << (10 + (i % 8))) for i in range(32)]
jump_points = [coincurve.PrivateKey.from_int(j).public_key for j in jump_sizes]

print("Iniciando Verificação Pollard's Kangaroo para Puzzle #30...", flush=True)

num_wild = 64
num_tame = 64

wild_dists = [range_start + (i * 1000) for i in range(num_wild)]
wild_pts = [coincurve.PrivateKey.from_int(d).public_key for d in wild_dists]

tame_scalars = [i * 1000 for i in range(num_tame)]
tame_dists = [(-s) % SECP256K1_N for s in tame_scalars]
tame_pts = []
for s in tame_scalars:
    neg_s = (SECP256K1_N - s) % SECP256K1_N
    if neg_s == 0: neg_s = 1
    neg_sg_pt = coincurve.PrivateKey.from_int(neg_s).public_key
    tame_pt = coincurve.PublicKey.combine_keys([target_pk, neg_sg_pt])
    tame_pts.append(tame_pt)

dp_mask = 0x1F # 5 DP bits (1 DP cada 32 passos)
dp_db = {}
found = False

for step in range(1, 100000):
    for i in range(num_wild):
        pt_bytes = wild_pts[i].format(compressed=True)
        idx = pt_bytes[-1] % 32
        wild_pts[i] = coincurve.PublicKey.combine_keys([wild_pts[i], jump_points[idx]])
        wild_dists[i] = (wild_dists[i] + jump_sizes[idx]) % SECP256K1_N
        
        x_val = int.from_bytes(pt_bytes[1:33], 'big')
        if (x_val & dp_mask) == 0:
            if x_val in dp_db:
                other_is_wild, other_dist = dp_db[x_val]
                if not other_is_wild:
                    priv_key = (wild_dists[i] - other_dist) % SECP256K1_N
                    print(f"\n=======================================================", flush=True)
                    print(f"!!! COLISÃO KANGAROO CONFIRMADA NO PASSO {step} !!!", flush=True)
                    print(f"Chave Privada Encontrada (HEX) = {hex(priv_key).upper()}", flush=True)
                    print(f"Target PubKey Validada        = {target_hex}", flush=True)
                    print(f"=======================================================\n", flush=True)
                    found = True
                    break
            else:
                dp_db[x_val] = (True, wild_dists[i])
    if found: break

    for i in range(num_tame):
        pt_bytes = tame_pts[i].format(compressed=True)
        idx = pt_bytes[-1] % 32
        tame_pts[i] = coincurve.PublicKey.combine_keys([tame_pts[i], jump_points[idx]])
        tame_dists[i] = (tame_dists[i] + jump_sizes[idx]) % SECP256K1_N
        
        x_val = int.from_bytes(pt_bytes[1:33], 'big')
        if (x_val & dp_mask) == 0:
            if x_val in dp_db:
                other_is_wild, other_dist = dp_db[x_val]
                if other_is_wild:
                    priv_key = (other_dist - tame_dists[i]) % SECP256K1_N
                    print(f"\n=======================================================", flush=True)
                    print(f"!!! COLISÃO KANGAROO CONFIRMADA NO PASSO {step} !!!", flush=True)
                    print(f"Chave Privada Encontrada (HEX) = {hex(priv_key).upper()}", flush=True)
                    print(f"Target PubKey Validada        = {target_hex}", flush=True)
                    print(f"=======================================================\n", flush=True)
                    found = True
                    break
            else:
                dp_db[x_val] = (False, tame_dists[i])
    if found: break

    if step % 2000 == 0:
        print(f"Passo {step} | DPs na memória: {len(dp_db)}", flush=True)
