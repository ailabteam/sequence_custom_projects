# ~/sequence_custom_projects/projects/hardware_tests/two_node_eg_custom.py

import time
import sys
from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.resource_management.rule_manager import Rule
# SỬA LỖI #1: Thay EntanglementGenerationA bằng BarretKokA
from sequence.entanglement_management.generation.barret_kok import BarretKokA 
from sequence.constants import MILLISECOND
from sequence.components.memory import MemoryArray # Cần để access T1

# =======================================================
# LOGIC GIAO THỨC (RULES)
# =======================================================

# 1. Rule Condition (Giữ nguyên)
def eg_rule_condition(memory_info, manager, args):
    if memory_info.state == "RAW":
        return [memory_info]
    else:
        return []

# 2. Rule Action 1 (Router R1 - Primary)
def eg_rule_action1(memories_info, args):
    def eg_req_func(protocols, args):
        for protocol in protocols:
            # SỬA LỖI #2: Kiểm tra BarretKokA thay vì EntanglementGenerationA
            if isinstance(protocol, BarretKokA): 
                return protocol
            
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    
    # SỬA LỖI #3: Khởi tạo BarretKokA
    # BarretKokA(owner=None, name, middle="m1", other="r2", memory)
    protocol = BarretKokA(None, "EGA." + memory.name, "m1", "r2", memory)
    protocol.primary = True
    
    # [protocol, [destination nodes], [destination conditions], [arguments]]
    return [protocol, ["r2"], [eg_req_func], [None]]

# 3. Rule Action 2 (Router R2 - Secondary)
def eg_rule_action2(memories_info, args):
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    
    # SỬA LỖI #4: Khởi tạo BarretKokA
    # BarretKokA(owner=None, name, middle="m1", other="r1", memory)
    protocol = BarretKokA(None, "EGA." + memory.name, "m1", "r1", memory)
    return [protocol, [None], [None], [None]]


# =======================================================
# HÀM MÔ PHỎNG VÀ TÙY CHỈNH T1
# =======================================================

def run_entanglement_test(t1_value: float, name: str):
    
    # Tham số mô phỏng cố định
    sim_time_ms = 1000  # 1s
    cc_delay_ms = 1     # 1ms
    qc_atten = 1e-4     # 0.0001 db/m
    qc_dist_km = 10     # 10km

    PS_PER_MS = 1e9
    M_PER_KM = 1e3
    
    # Chuyển đổi đơn vị
    cc_delay = cc_delay_ms * PS_PER_MS
    qc_dist = qc_dist_km * M_PER_KM
    sim_time_ps = sim_time_ms * PS_PER_MS

    print(f"\n=======================================================")
    print(f"Bắt đầu mô phỏng: {name} (T1={t1_value:.0e}s)")

    # 1. Khởi tạo Timeline
    tl = Timeline(sim_time_ps) 

    # 2. Xây dựng Topology
    r1 = QuantumRouter("r1", tl, 50) # 50 memories
    r2 = QuantumRouter("r2", tl, 50)
    m1 = BSMNode("m1", tl, ["r1", "r2"]) # BSMNode tự động kết nối QLink/CLink với r1, r2
    
    r1.set_seed(0)
    r2.set_seed(1)
    m1.set_seed(2)
    
    # 3. Tùy chỉnh Hardware (Memory T1)
    for node in [r1, r2]:
        # Lấy Memory Array Component
        memory_array = node.get_components_by_type("MemoryArray")[0]
        
        # ÁP DỤNG CUSTOM T1
        # T1 được đo bằng giây (s). 
        # Phương thức này cập nhật tham số T1/T2 của TẤT CẢ các Memory trong mảng.
        memory_array.update_memory_params("coherence_time", t1_value)
    
    # 4. Kết nối Channel (Lấy từ Notebook)
    nodes = [r1, r2, m1]
    
    # Kết nối cổ điển (All-to-All)
    for node1 in nodes:
        for node2 in nodes:
            if node1 == node2:
                continue
            # ClassicalChannel nhận distance (m) và delay (ps)
            cc = ClassicalChannel("_".join(["cc", node1.name, node2.name]), tl, qc_dist, delay=cc_delay)
            cc.set_ends(node1, node2.name) 
    
    # Kết nối lượng tử (Linear r1 - m1 - r2)
    # QuantumChannel nhận attenuation (db/m) và distance (m)
    qc1 = QuantumChannel("qc_r1_m1", tl, qc_atten, qc_dist)
    qc1.set_ends(r1, m1.name)
    qc2 = QuantumChannel("qc_r2_m1", tl, qc_atten, qc_dist)
    qc2.set_ends(r2, m1.name)
    
    # 5. Cài đặt Rules và Chạy mô phỏng
    tl.init()
    
    # Cài đặt Rules (Priority 10)
    rule1 = Rule(10, eg_rule_action1, eg_rule_condition, None, None)
    r1.resource_manager.load(rule1)
    rule2 = Rule(10, eg_rule_action2, eg_rule_condition, None, None)
    r2.resource_manager.load(rule2)
    
    tick = time.time()
    tl.run() 
    print("execution time %.2f sec" % (time.time() - tick))
    
    # 6. Thu thập và Báo cáo Metrics
    
    entangled_count = 0
    
    # Tổng hợp entanglement từ cả hai router
    for router in [r1, r2]:
        for info in router.resource_manager.memory_manager:
            if info.entangle_time > 0:
                entangled_count += 1

    print(f"--- Kết quả Mô phỏng {name} ---")
    print(f"T1 Quantum Memory: {t1_value:.0e}s")
    print(f"Tổng số cặp vướng víu thành công: {entangled_count}")
    
    if sim_time_ms > 0 and entangled_count > 0:
        rate = entangled_count / sim_time_ms * 1000 
        print(f"Tốc độ vướng víu (pairs/s): {rate:.2f}")
    else:
        print("Mô phỏng không tạo ra cặp vướng víu nào.")


# =======================================================
# THỰC THI CHÍNH
# =======================================================

T1_LOW = 1e-6  # 1 micro giây
T1_HIGH = 1e-3 # 1 mili giây (Tùy chỉnh)

run_entanglement_test(T1_LOW, "LOW_T1")
run_entanglement_test(T1_HIGH, "HIGH_T1_CUSTOM")

print("\n--- BÀI TẬP CUSTOM HARDWARE HOÀN TẤT ---")
