# ~/sequence_custom_projects/projects/hardware_tests/run_t1_comparison_final.py

# =======================================================
# IMPORTS (Lấy từ Notebook)
# =======================================================
from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.resource_management.rule_manager import Rule
from sequence.entanglement_management.generation import EntanglementGenerationA
from sequence.constants import MILLISECOND
import time
import sys

# =======================================================
# LOGIC GIAO THỨC (Rules - Lấy từ Notebook)
# =======================================================

def eg_rule_condition(memory_info, manager, args):
    if memory_info.state == "RAW":
        return [memory_info]
    else:
        return []

def eg_rule_action1(memories_info, args):
    def eg_req_func(protocols, args):
        for protocol in protocols:
            if isinstance(protocol, EntanglementGenerationA):
                return protocol
            
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    # r1 (owner) liên kết với BSM 'm1' và node đối diện 'r2'
    protocol = EntanglementGenerationA(None, "EGA." + memory.name, "m1", "r2", memory)
    protocol.primary = True
    
    return [protocol, ["r2"], [eg_req_func], [None]]

def eg_rule_action2(memories_info, args):
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    # r2 (owner) liên kết với BSM 'm1' và node đối diện 'r1'
    protocol = EntanglementGenerationA(None, "EGA." + memory.name, "m1", "r1", memory)
    return [protocol, [None], [None], [None]]


# =======================================================
# HÀM MÔ PHỎNG VÀ TÙY CHỈNH T1
# =======================================================

def run_entanglement_test(t1_value: float, name: str):
    """
    Chạy mô phỏng EG 2-node với T1 cụ thể và báo cáo kết quả.
    """
    
    # Tham số cố định (Lấy từ giá trị mặc định của Notebook)
    sim_time_ms = 1000  # 1s
    cc_delay_ms = 1     # 1ms
    qc_atten = 1e-4     # 0.0001 db/m
    qc_dist_km = 10     # 10km

    PS_PER_MS = 1e9
    M_PER_KM = 1e3
    
    # Chuyển đổi đơn vị
    cc_delay = cc_delay_ms * PS_PER_MS
    qc_dist = qc_dist_km * M_PER_KM
    sim_time = sim_time_ms * PS_PER_MS

    print(f"\n=======================================================")
    print(f"Bắt đầu mô phỏng: {name} (T1={t1_value:.0e}s)")

    # 1. Khởi tạo Timeline
    tl = Timeline(sim_time) # sim_time được truyền vào như MAX_TIME

    # 2. Xây dựng Topology
    r1 = QuantumRouter("r1", tl, 50)
    r2 = QuantumRouter("r2", tl, 50)
    # BSMNode tự động kết nối với các router được liệt kê
    m1 = BSMNode("m1", tl, ["r1", "r2"])
    
    r1.set_seed(0)
    r2.set_seed(1)
    m1.set_seed(2)
    
    # 3. Tùy chỉnh Hardware (Memory T1)
    for node in [r1, r2]:
        memory_array = node.get_components_by_type("MemoryArray")[0]
        
        # *********** CUSTOMIZATION: THAY ĐỔI T1 (Coherence Time) ***********
        # T1 được đo bằng giây (s). 
        memory_array.update_memory_params("coherence_time", t1_value)
        # *******************************************************************
    
    # 4. Kết nối Channel (All-to-All Classical, Linear Quantum)
    nodes = [r1, r2, m1]
    
    # Kết nối cổ điển (Classical Channels)
    for node1 in nodes:
        for node2 in nodes:
            if node1 == node2:
                continue
            cc = ClassicalChannel("_".join(["cc", node1.name, node2.name]), tl, qc_dist, delay=cc_delay)
            # Notebook sử dụng set_ends, không phải assign_cchannel!
            cc.set_ends(node1, node2.name) 
    
    # Kết nối lượng tử (Quantum Channels)
    qc1 = QuantumChannel("qc_r1_m1", tl, qc_atten, qc_dist)
    qc1.set_ends(r1, m1.name)
    qc2 = QuantumChannel("qc_r2_m1", tl, qc_atten, qc_dist)
    qc2.set_ends(r2, m1.name)
    
    # 5. Cài đặt Rules và Chạy mô phỏng
    tl.init()
    
    # Cài đặt Rules cho Resource Manager
    rule1 = Rule(10, eg_rule_action1, eg_rule_condition, None, None)
    r1.resource_manager.load(rule1)
    rule2 = Rule(10, eg_rule_action2, eg_rule_condition, None, None)
    r2.resource_manager.load(rule2)
    
    tick = time.time()
    tl.run() # Chạy đến sim_time đã định nghĩa trong Timeline constructor
    print("execution time %.2f sec" % (time.time() - tick))
    
    # 6. Thu thập và Báo cáo Metrics
    
    # Số lượng entanglement thành công được lưu trữ trong memory_manager
    entangled_count = 0
    total_entanglement_time = 0
    
    # Duyệt qua các memory của r1 để đếm entanglement thành công
    for info in r1.resource_manager.memory_manager:
        if info.entangle_time > 0:
            entangled_count += 1
            total_entanglement_time += info.entangle_time
            
    # Duyệt qua các memory của r2
    for info in r2.resource_manager.memory_manager:
        if info.entangle_time > 0:
            entangled_count += 1
            total_entanglement_time += info.entangle_time

    print(f"--- Kết quả Mô phỏng {name} ---")
    print(f"T1 Quantum Memory: {t1_value:.0e}s")
    print(f"Tổng số cặp vướng víu thành công: {entangled_count}")
    
    if entangled_count > 0:
        # Tính Entanglement Rate thô (pairs/s)
        rate = entangled_count / sim_time_ms * 1000 
        print(f"Tốc độ vướng víu (pairs/s): {rate:.2f}")


# =======================================================
# THỰC THI CHÍNH
# =======================================================

T1_LOW = 1e-6  # 1 micro giây
T1_HIGH = 1e-3 # 1 mili giây (Tùy chỉnh)

run_entanglement_test(T1_LOW, "LOW_T1")
run_entanglement_test(T1_HIGH, "HIGH_T1_CUSTOM")

print("\nKiểm tra tùy chỉnh Hardware (T1 Lifetime) hoàn tất.")
